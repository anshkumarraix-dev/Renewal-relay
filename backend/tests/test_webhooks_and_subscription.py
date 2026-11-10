"""Integration tests for Webhook Ingestion, Deduplication, and Subscription Intelligence (P2 & P3).

Architectural Guarantees:
- Event ID deduplication is strictly enforced.
- Replays do not trigger duplicate database state transitions.
- Authoritative state updates for subscriptions, failures, and sales.
"""

import unittest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.webhook_service import WebhookService
from app.services.subscription_service import SubscriptionService
from app.models.subscription import Subscription, PaymentFailure, PaymentTransaction, SubscriptionStateHistory
from app.models.webhook import WebhookEvent
from app.models.recovery import RecoveryOpportunity


class TestWebhooksAndSubscription(unittest.TestCase):
    """Test webhook processing, event deduplication, and state tracking."""

    def setUp(self):
        # In-memory SQLite for isolated test execution
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.webhook_service = WebhookService(self.db, paypal_service=None)
        self.sub_service = SubscriptionService(self.db, paypal_service=None)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_webhook_event_deduplication(self):
        """Verify that sending the same event ID twice returns already_processed."""
        event_payload = {
            "id": "WH-EVT-DEDUP-001",
            "event_type": "BILLING.SUBSCRIPTION.CREATED",
            "resource_type": "subscription",
            "summary": "Subscription created",
            "resource": {
                "id": "I-SUB-DEDUP-1",
                "status": "ACTIVE",
                "subscriber": {"email_address": "user@test.local"},
            },
        }

        async def run_dedup():
            # First ingestion
            status1, eid1, _ = await self.webhook_service.ingest_event(
                headers={},
                raw_body_bytes=b"{}",
                event_json=event_payload,
            )
            self.assertEqual(status1, "received")
            self.assertEqual(eid1, "WH-EVT-DEDUP-001")

            # Duplicate ingestion (replay)
            status2, eid2, msg2 = await self.webhook_service.ingest_event(
                headers={},
                raw_body_bytes=b"{}",
                event_json=event_payload,
            )
            self.assertEqual(status2, "already_processed")
            self.assertEqual(eid2, "WH-EVT-DEDUP-001")
            self.assertIn("already processed", msg2.lower())

            # Verify only 1 webhook record exists in DB
            events = self.db.query(WebhookEvent).filter(WebhookEvent.paypal_event_id == "WH-EVT-DEDUP-001").all()
            self.assertEqual(len(events), 1)

        asyncio.run(run_dedup())

    def test_payment_failed_event_triggers_recovery_opportunity(self):
        """Verify BILLING.SUBSCRIPTION.PAYMENT.FAILED creates failure and recovery opportunity."""
        # 1. Pre-seed subscription
        sub = Subscription(
            id="I-SUB-FAIL-100",
            status="ACTIVE",
            outstanding_balance_amount=0.0,
            currency="USD",
            failed_payment_count=0,
        )
        self.db.add(sub)
        self.db.commit()

        event_payload = {
            "id": "WH-EVT-FAIL-002",
            "event_type": "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
            "resource_type": "subscription",
            "resource": {
                "billing_agreement_id": "I-SUB-FAIL-100",
                "amount": {"value": "89.00", "currency_code": "USD"},
                "status_code": "INSUFFICIENT_FUNDS",
                "status_reason": "Not enough balance",
            },
        }

        async def run_fail():
            status, eid, _ = await self.webhook_service.ingest_event(
                headers={},
                raw_body_bytes=b"{}",
                event_json=event_payload,
            )
            self.assertEqual(status, "received")

            # Verify subscription state
            updated_sub = self.db.get(Subscription, "I-SUB-FAIL-100")
            self.assertEqual(updated_sub.failed_payment_count, 1)
            self.assertEqual(updated_sub.outstanding_balance_amount, 89.00)

            # Verify payment failure record
            failures = self.db.query(PaymentFailure).filter(PaymentFailure.subscription_id == "I-SUB-FAIL-100").all()
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0].amount, 89.00)
            self.assertEqual(failures[0].failure_reason_code, "INSUFFICIENT_FUNDS")

            # Verify recovery opportunity created
            opps = self.db.query(RecoveryOpportunity).filter(RecoveryOpportunity.subscription_id == "I-SUB-FAIL-100").all()
            self.assertEqual(len(opps), 1)
            self.assertEqual(opps[0].status, "ELIGIBLE")
            self.assertEqual(opps[0].eligible_amount, 89.00)

        asyncio.run(run_fail())

    def test_payment_sale_completed_updates_balance_and_transactions(self):
        """Verify PAYMENT.SALE.COMPLETED updates balance and logs PaymentTransaction."""
        sub = Subscription(
            id="I-SUB-SALE-200",
            status="ACTIVE",
            outstanding_balance_amount=89.00,
            currency="USD",
            failed_payment_count=1,
        )
        self.db.add(sub)
        self.db.commit()

        event_payload = {
            "id": "WH-EVT-SALE-003",
            "event_type": "PAYMENT.SALE.COMPLETED",
            "resource_type": "sale",
            "resource": {
                "id": "SALE-TX-999",
                "billing_agreement_id": "I-SUB-SALE-200",
                "amount": {"total": "89.00", "currency": "USD"},
            },
        }

        async def run_sale():
            status, _, _ = await self.webhook_service.ingest_event(
                headers={},
                raw_body_bytes=b"{}",
                event_json=event_payload,
            )
            self.assertEqual(status, "received")

            updated_sub = self.db.get(Subscription, "I-SUB-SALE-200")
            self.assertEqual(updated_sub.outstanding_balance_amount, 0.0)
            self.assertEqual(updated_sub.failed_payment_count, 0)
            self.assertEqual(updated_sub.last_payment_amount, 89.00)

            # Verify transaction record
            txs = self.db.query(PaymentTransaction).filter(PaymentTransaction.subscription_id == "I-SUB-SALE-200").all()
            self.assertEqual(len(txs), 1)
            self.assertEqual(txs[0].transaction_type, "SALE")
            self.assertEqual(txs[0].amount, 89.00)
            self.assertEqual(txs[0].status, "COMPLETED")

        asyncio.run(run_sale())


if __name__ == "__main__":
    unittest.main()
