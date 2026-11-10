"""Subscription Intelligence and State Tracking Service.

Architectural Guarantees:
- PayPal remains the external payment authority.
- Synchronizes and normalizes subscription details and billing cycles.
- Persists state transitions with audit trail.
- Detects recovery opportunities for eligible subscriptions.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.subscription import (
    Merchant,
    BillingPlan,
    Subscription,
    PaymentTransaction,
    PaymentFailure,
    SubscriptionStateHistory,
)
from app.models.recovery import RecoveryOpportunity
from app.services.paypal_service import PayPalService
from app.services.recovery_policy_service import RecoveryPolicyEngine
from app.services.ai_service import AIIntelligenceService

logger = logging.getLogger("renewal_relay.services.subscription")


def parse_paypal_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse PayPal ISO 8601 datetime strings safely."""
    if not dt_str:
        return None
    try:
        # Replace 'Z' with '+00:00' for standard fromisoformat parsing
        clean_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        return None


class SubscriptionService:
    """Manages subscription state, transaction synchronization, and recovery opportunity detection."""

    def __init__(self, db: Session, paypal_service: Optional[PayPalService] = None):
        self.db = db
        self.paypal = paypal_service

    def get_or_create_merchant(self, merchant_id: str = "default_merchant", name: str = "Renewal Relay Demo Merchant") -> Merchant:
        """Ensure a default merchant record exists."""
        merchant = self.db.get(Merchant, merchant_id)
        if not merchant:
            merchant = Merchant(
                id=merchant_id,
                name=name,
                email="merchant@renewalrelay.local",
            )
            self.db.add(merchant)
            self.db.commit()
            self.db.refresh(merchant)
        return merchant

    def sync_subscription_from_paypal_data(self, data: Dict[str, Any], merchant_id: Optional[str] = None) -> Subscription:
        """Upsert a subscription record from PayPal Sandbox API response or webhook payload."""
        sub_id = data.get("id")
        if not sub_id:
            raise ValueError("Subscription payload missing required 'id' attribute.")

        merchant = self.get_or_create_merchant(merchant_id or "default_merchant")
        sub = self.db.get(Subscription, sub_id)

        plan_id = data.get("plan_id")
        status = (data.get("status") or "ACTIVE").upper()

        # Extract subscriber details
        subscriber = data.get("subscriber", {})
        name_obj = subscriber.get("name", {})
        subscriber_name = f"{name_obj.get('given_name', '')} {name_obj.get('surname', '')}".strip() or None
        subscriber_email = subscriber.get("email_address")

        # Extract billing info
        billing_info = data.get("billing_info", {})
        outstanding = billing_info.get("outstanding_balance", {})
        outstanding_amount = float(outstanding.get("value", 0.0))
        currency = outstanding.get("currency_code", "USD")
        failed_count = int(billing_info.get("failed_payments_count", 0))

        next_billing_time = parse_paypal_datetime(billing_info.get("next_billing_time"))
        last_payment = billing_info.get("last_payment", {})
        last_payment_time = parse_paypal_datetime(last_payment.get("time"))
        last_payment_amount = float(last_payment.get("amount", {}).get("value", 0.0)) if last_payment.get("amount") else None

        if sub is None:
            sub = Subscription(
                id=sub_id,
                plan_id=plan_id,
                merchant_id=merchant.id,
                status=status,
                subscriber_name=subscriber_name,
                subscriber_email=subscriber_email,
                outstanding_balance_amount=outstanding_amount,
                currency=currency,
                failed_payment_count=failed_count,
                next_billing_time=next_billing_time,
                last_payment_time=last_payment_time,
                last_payment_amount=last_payment_amount,
            )
            self.db.add(sub)
            # Log initial state
            history = SubscriptionStateHistory(
                id=str(uuid.uuid4()),
                subscription_id=sub_id,
                previous_status=None,
                new_status=status,
                reason="Initial ingestion",
                source="API_SYNC",
            )
            self.db.add(history)
        else:
            previous_status = sub.status
            sub.plan_id = plan_id or sub.plan_id
            sub.status = status
            if subscriber_name:
                sub.subscriber_name = subscriber_name
            if subscriber_email:
                sub.subscriber_email = subscriber_email
            sub.outstanding_balance_amount = outstanding_amount
            sub.currency = currency
            sub.failed_payment_count = failed_count
            sub.next_billing_time = next_billing_time
            if last_payment_time:
                sub.last_payment_time = last_payment_time
                sub.last_payment_amount = last_payment_amount

            # If status transitioned, record audit history
            if previous_status != status:
                history = SubscriptionStateHistory(
                    id=str(uuid.uuid4()),
                    subscription_id=sub_id,
                    previous_status=previous_status,
                    new_status=status,
                    reason=f"Status changed from {previous_status} to {status}",
                    source="API_SYNC",
                )
                self.db.add(history)

        self.db.commit()
        self.db.refresh(sub)

        # Evaluate if this subscription qualifies as a recovery opportunity
        if sub.outstanding_balance_amount > 0 and sub.failed_payment_count >= 1:
            self.ensure_recovery_opportunity(sub)

        return sub

    def record_payment_failure(
        self,
        subscription_id: str,
        amount: float,
        currency: str,
        reason_code: Optional[str] = None,
        reason_message: Optional[str] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> PaymentFailure:
        """Record an explicit payment failure event for a subscription."""
        sub = self.db.get(Subscription, subscription_id)
        if sub:
            sub.failed_payment_count += 1
            if amount > 0:
                sub.outstanding_balance_amount += amount

        failure = PaymentFailure(
            id=str(uuid.uuid4()),
            subscription_id=subscription_id,
            amount=amount,
            currency=currency,
            failure_reason_code=reason_code,
            failure_message=reason_message,
            raw_payload=raw_payload,
            occurred_at=datetime.now(timezone.utc),
        )
        self.db.add(failure)
        self.db.commit()

        if sub:
            self.db.refresh(sub)
            self.ensure_recovery_opportunity(sub, failure)

        return failure

    def ensure_recovery_opportunity(
        self,
        subscription: Subscription,
        latest_failure: Optional[PaymentFailure] = None,
    ) -> RecoveryOpportunity:
        """Ensure an active RecoveryOpportunity exists and run initial deterministic evaluation."""
        stmt = (
            select(RecoveryOpportunity)
            .where(RecoveryOpportunity.subscription_id == subscription.id)
            .where(RecoveryOpportunity.status.in_(["IDENTIFIED", "ELIGIBLE", "PENDING_APPROVAL"]))
        )
        opp = self.db.execute(stmt).scalar_one_or_none()

        if not opp:
            opp = RecoveryOpportunity(
                id=str(uuid.uuid4()),
                subscription_id=subscription.id,
                status="IDENTIFIED",
                eligible_amount=subscription.outstanding_balance_amount,
                currency=subscription.currency,
                detected_at=datetime.now(timezone.utc),
            )
            self.db.add(opp)
            self.db.commit()
            self.db.refresh(opp)

        # Run deterministic evaluation
        from app.models.recovery import RecoveryEvaluation, AIRecommendation

        eval_result = RecoveryPolicyEngine.evaluate(
            subscription_status=subscription.status,
            outstanding_balance=subscription.outstanding_balance_amount,
            currency=subscription.currency,
            failed_payment_count=subscription.failed_payment_count,
            next_billing_time=subscription.next_billing_time,
        )

        evaluation = RecoveryEvaluation(
            id=str(uuid.uuid4()),
            opportunity_id=opp.id,
            is_eligible=eval_result.is_eligible,
            decision=eval_result.decision,
            reason=eval_result.reason,
            evidence_json=eval_result.evidence,
            policy_version=eval_result.policy_version,
            suggested_action=eval_result.suggested_action,
        )
        self.db.add(evaluation)

        # Run AI Failure Analysis
        reason_code = latest_failure.failure_reason_code if latest_failure else None
        reason_msg = latest_failure.failure_message if latest_failure else None

        ai_result = AIIntelligenceService.analyze_failure(
            failure_code=reason_code,
            failure_message=reason_msg,
            failed_count=subscription.failed_payment_count,
            outstanding_balance=subscription.outstanding_balance_amount,
            currency=subscription.currency,
            subscription_status=subscription.status,
            has_future_retry=eval_result.decision == "WAITING_NATIVE_RETRY",
        )

        ai_rec = AIRecommendation(
            id=str(uuid.uuid4()),
            opportunity_id=opp.id,
            subscription_id=subscription.id,
            failure_category=ai_result.failure_category,
            confidence_score=ai_result.confidence_score,
            explanation=ai_result.explanation,
            evidence_json={"points": ai_result.evidence, "missing": ai_result.missing_information},
            recommended_action=ai_result.recommended_action,
            suggested_action_type=ai_result.suggested_action_type,
        )
        self.db.add(ai_rec)

        if eval_result.is_eligible:
            opp.status = "ELIGIBLE"
        else:
            if opp.status not in ("APPROVED", "EXECUTING", "RECOVERED"):
                opp.status = "IDENTIFIED"

        self.db.commit()
        self.db.refresh(opp)
        return opp

    def list_subscriptions(self, status: Optional[str] = None, limit: int = 50) -> List[Subscription]:
        """Query subscriptions with optional status filter."""
        stmt = select(Subscription).order_by(desc(Subscription.updated_at)).limit(limit)
        if status:
            stmt = stmt.where(Subscription.status == status.upper())
        return list(self.db.execute(stmt).scalars().all())

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Fetch subscription by ID."""
        return self.db.get(Subscription, subscription_id)
