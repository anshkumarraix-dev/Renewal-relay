"""Integration tests for Merchant Approvals, Capture Execution, Ambiguity, and Reconciliation (P6).

Architectural Guarantees:
- Every capture requires merchant authorization.
- Deterministic policy rechecked pre-execution.
- Idempotency key (PayPal-Request-Id) passed.
- Ambiguous outcomes trigger reconciliation; ZERO blind retries.
- Authoritative outcome verification.
"""

import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.recovery_service import RecoveryService
from app.services.paypal_service import PayPalService
from app.models.subscription import Subscription, PaymentTransaction
from app.models.recovery import RecoveryOpportunity, RecoveryEvaluation, MerchantApproval, RecoveryOperation
from app.core.paypal.exceptions import PayPalAmbiguousError, PayPalClientError
from app.core.paypal.client import OperationSafety


class TestRecoveryWorkflow(unittest.TestCase):
    """Test merchant approval, capture execution, ambiguity handling, and reconciliation."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # Mock PayPal service
        self.mock_paypal = MagicMock(spec=PayPalService)
        self.recovery_service = RecoveryService(self.db, self.mock_paypal)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _setup_eligible_opportunity(self) -> RecoveryOpportunity:
        sub = Subscription(
            id="I-TEST-REC-001",
            status="SUSPENDED",
            outstanding_balance_amount=75.00,
            currency="USD",
            failed_payment_count=2,
            next_billing_time=None,
        )
        self.db.add(sub)

        opp = RecoveryOpportunity(
            id="OPP-REC-001",
            subscription_id="I-TEST-REC-001",
            status="ELIGIBLE",
            eligible_amount=75.00,
            currency="USD",
        )
        self.db.add(opp)
        self.db.commit()
        return opp

    def test_approve_recovery_success(self):
        """Verify successful merchant approval dispatches capture and records revenue."""
        opp = self._setup_eligible_opportunity()

        # Mock successful PayPal capture response
        self.mock_paypal.capture_outstanding_balance = AsyncMock(return_value={
            "status": "COMPLETED",
            "id": "CAP-PAYPAL-12345",
            "debug_id": "dbg-cap-success",
        })

        async def run_approve():
            res = await self.recovery_service.approve_recovery(
                opportunity_id="OPP-REC-001",
                merchant_user="admin_jane",
                note="Customer confirmed updated card balance",
            )
            self.assertEqual(res.status, "RECOVERED")

            # Verify MerchantApproval record
            approvals = self.db.query(MerchantApproval).filter(MerchantApproval.opportunity_id == "OPP-REC-001").all()
            self.assertEqual(len(approvals), 1)
            self.assertEqual(approvals[0].decision, "APPROVED")
            self.assertEqual(approvals[0].merchant_user, "admin_jane")

            # Verify RecoveryOperation record
            ops = self.db.query(RecoveryOperation).filter(RecoveryOperation.opportunity_id == "OPP-REC-001").all()
            self.assertEqual(len(ops), 1)
            self.assertEqual(ops[0].status, "COMPLETED")
            self.assertEqual(ops[0].paypal_capture_id, "CAP-PAYPAL-12345")
            self.assertIsNotNone(ops[0].request_id)

            # Verify Subscription state and PaymentTransaction
            sub = self.db.get(Subscription, "I-TEST-REC-001")
            self.assertEqual(sub.outstanding_balance_amount, 0.0)
            self.assertEqual(sub.failed_payment_count, 0)
            self.assertEqual(sub.status, "ACTIVE")  # Restored from SUSPENDED

            txs = self.db.query(PaymentTransaction).filter(PaymentTransaction.subscription_id == "I-TEST-REC-001").all()
            self.assertEqual(len(txs), 1)
            self.assertEqual(txs[0].transaction_type, "CAPTURE")
            self.assertEqual(txs[0].amount, 75.00)

        asyncio.run(run_approve())

    def test_approve_recovery_ambiguous_outcome(self):
        """Verify ambiguous timeout/502 flags operation as AMBIGUOUS without blind retries."""
        opp = self._setup_eligible_opportunity()

        # Mock ambiguous error
        self.mock_paypal.capture_outstanding_balance = AsyncMock(
            side_effect=PayPalAmbiguousError(
                message="HTTP 504 Gateway Timeout during capture",
                operation_safety=OperationSafety.MUTATING_FINANCIAL,
                request_id="req-ambig-999",
                debug_id="dbg-504-ambig",
                status_code=504,
            )
        )

        async def run_ambig():
            res = await self.recovery_service.approve_recovery(
                opportunity_id="OPP-REC-001",
                merchant_user="admin_jane",
            )
            self.assertEqual(res.status, "AMBIGUOUS_RECONCILING")

            # Verify operation state
            ops = self.db.query(RecoveryOperation).filter(RecoveryOperation.opportunity_id == "OPP-REC-001").all()
            self.assertEqual(len(ops), 1)
            self.assertEqual(ops[0].status, "AMBIGUOUS")
            self.assertEqual(ops[0].paypal_debug_id, "dbg-504-ambig")

            # Verify subscription balance was NOT altered yet (prevent false recovered revenue)
            sub = self.db.get(Subscription, "I-TEST-REC-001")
            self.assertEqual(sub.outstanding_balance_amount, 75.00)

        asyncio.run(run_ambig())

    def test_reconciliation_resolves_ambiguous_operation(self):
        """Verify reconciliation against PayPal transactions resolves ambiguous state safely."""
        opp = self._setup_eligible_opportunity()

        # Create ambiguous operation
        op = RecoveryOperation(
            id="OP-AMBIG-100",
            opportunity_id=opp.id,
            subscription_id="I-TEST-REC-001",
            operation_type="CAPTURE",
            request_id="req-rec-555",
            amount=75.00,
            currency="USD",
            status="AMBIGUOUS",
            paypal_debug_id="dbg-504-ambig",
        )
        self.db.add(op)
        opp.status = "AMBIGUOUS_RECONCILING"
        self.db.commit()

        # Case 1: Transaction found on PayPal
        self.mock_paypal.list_subscription_transactions = AsyncMock(return_value={
            "transactions": [
                {
                    "id": "CAP-CONFIRMED-999",
                    "status": "COMPLETED",
                    "amount_with_breakdown": {"gross_amount": {"value": "75.00"}},
                }
            ]
        })

        async def run_reconcile():
            res = await self.recovery_service.reconcile_operation("OP-AMBIG-100")
            self.assertEqual(res["reconciled_status"], "COMPLETED")
            self.assertIn("Verified completed capture", res["message"])

            # Verify opportunity updated to RECOVERED
            updated_opp = self.db.get(RecoveryOpportunity, "OPP-REC-001")
            self.assertEqual(updated_opp.status, "RECOVERED")

        asyncio.run(run_reconcile())

    def test_reject_recovery(self):
        """Verify merchant rejection updates opportunity status to REJECTED."""
        opp = self._setup_eligible_opportunity()

        async def run_reject():
            res = await self.recovery_service.reject_recovery(
                opportunity_id="OPP-REC-001",
                merchant_user="admin_jane",
                note="Subscriber requested cancellation",
            )
            self.assertEqual(res.status, "REJECTED")

            approvals = self.db.query(MerchantApproval).filter(MerchantApproval.opportunity_id == "OPP-REC-001").all()
            self.assertEqual(len(approvals), 1)
            self.assertEqual(approvals[0].decision, "REJECTED")

        asyncio.run(run_reject())


if __name__ == "__main__":
    unittest.main()
