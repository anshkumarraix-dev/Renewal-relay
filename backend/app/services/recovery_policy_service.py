"""Deterministic Recovery Policy Engine.

Architectural Guarantees:
- Strictly separated from AI logic.
- Pure, deterministic, and 100% testable functions.
- The same inputs always produce the exact same decision and explainable evidence.
- AI cannot override or bypass policy evaluation outcomes.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class RecoveryEvaluationResult(BaseModel):
    is_eligible: bool
    decision: str  # ELIGIBLE, INELIGIBLE, WAITING_NATIVE_RETRY, REQUIRES_VERIFICATION, COOLDOWN_ACTIVE
    reason: str
    evidence: Dict[str, Any]
    policy_version: str = "v1.0.0"
    suggested_action: str


class RecoveryPolicyEngine:
    """Evaluates whether a failed or suspended subscription is eligible for balance capture."""

    POLICY_VERSION = "v1.0.0"
    MIN_CAPTURE_AMOUNT = 0.01
    COOLDOWN_HOURS = 24

    @classmethod
    def evaluate(
        cls,
        subscription_status: str,
        outstanding_balance: float,
        currency: str,
        failed_payment_count: int,
        next_billing_time: Optional[datetime] = None,
        last_operation_status: Optional[str] = None,
        last_operation_time: Optional[datetime] = None,
        current_time: Optional[datetime] = None,
    ) -> RecoveryEvaluationResult:
        """Evaluate recovery eligibility deterministically based on verified subscription state."""
        now = current_time or datetime.now(timezone.utc)
        sub_status = (subscription_status or "").strip().upper()

        evidence: Dict[str, Any] = {
            "subscription_status": sub_status,
            "outstanding_balance": outstanding_balance,
            "currency": currency,
            "failed_payment_count": failed_payment_count,
            "next_billing_time": next_billing_time.isoformat() if next_billing_time else None,
            "last_operation_status": last_operation_status,
            "last_operation_time": last_operation_time.isoformat() if last_operation_time else None,
            "evaluated_at": now.isoformat(),
        }

        # Rule 1: Check for existing in-flight or ambiguous operations
        if last_operation_status in ("INITIATED", "AMBIGUOUS"):
            return RecoveryEvaluationResult(
                is_eligible=False,
                decision="REQUIRES_VERIFICATION",
                reason=(
                    f"A previous recovery operation is currently in status '{last_operation_status}'. "
                    "Reconciliation is required before any subsequent operation can be initiated."
                ),
                evidence=evidence,
                policy_version=cls.POLICY_VERSION,
                suggested_action="RECONCILE_PREVIOUS_OPERATION",
            )

        # Rule 2: Subscription Status must be ACTIVE or SUSPENDED
        if sub_status not in ("ACTIVE", "SUSPENDED"):
            return RecoveryEvaluationResult(
                is_eligible=False,
                decision="INELIGIBLE",
                reason=(
                    f"Subscription status '{sub_status}' is not eligible for recovery capture. "
                    "Only ACTIVE or SUSPENDED subscriptions with outstanding balances are supported."
                ),
                evidence=evidence,
                policy_version=cls.POLICY_VERSION,
                suggested_action="NO_ACTION_REQUIRED",
            )

        # Rule 3: Outstanding balance must be greater than minimum threshold
        if outstanding_balance < cls.MIN_CAPTURE_AMOUNT:
            return RecoveryEvaluationResult(
                is_eligible=False,
                decision="INELIGIBLE",
                reason=(
                    f"Outstanding balance ({outstanding_balance:.2f} {currency}) is below minimum "
                    f"capture threshold ({cls.MIN_CAPTURE_AMOUNT:.2f} {currency})."
                ),
                evidence=evidence,
                policy_version=cls.POLICY_VERSION,
                suggested_action="NO_ACTION_REQUIRED",
            )

        # Rule 4: Must have at least 1 failed payment record
        if failed_payment_count < 1:
            return RecoveryEvaluationResult(
                is_eligible=False,
                decision="INELIGIBLE",
                reason="Subscription has no recorded failed payment occurrences.",
                evidence=evidence,
                policy_version=cls.POLICY_VERSION,
                suggested_action="WAIT_FOR_SCHEDULED_BILLING",
            )

        # Rule 5: Respect PayPal Native Retry Window
        # If PayPal has scheduled a native automated retry in the future, do not double-bill
        if next_billing_time and next_billing_time > now:
            time_until_retry = next_billing_time - now
            if time_until_retry < timedelta(days=5):
                return RecoveryEvaluationResult(
                    is_eligible=False,
                    decision="WAITING_NATIVE_RETRY",
                    reason=(
                        f"PayPal has scheduled a native automated renewal retry on "
                        f"{next_billing_time.strftime('%Y-%m-%d %H:%M UTC')}. "
                        "Awaiting native retry outcome before merchant intervention."
                    ),
                    evidence=evidence,
                    policy_version=cls.POLICY_VERSION,
                    suggested_action="AWAIT_NATIVE_RETRY",
                )

        # Rule 6: Enforce Cooldown Period between consecutive capture attempts
        if last_operation_time:
            cooldown_delta = timedelta(hours=cls.COOLDOWN_HOURS)
            if now - last_operation_time < cooldown_delta:
                remaining_hours = (last_operation_time + cooldown_delta - now).total_seconds() / 3600.0
                return RecoveryEvaluationResult(
                    is_eligible=False,
                    decision="COOLDOWN_ACTIVE",
                    reason=(
                        f"Recovery capture cooldown active. Last attempt occurred less than "
                        f"{cls.COOLDOWN_HOURS} hours ago ({remaining_hours:.1f} hours remaining)."
                    ),
                    evidence=evidence,
                    policy_version=cls.POLICY_VERSION,
                    suggested_action="AWAIT_COOLDOWN_EXPIRATION",
                )

        # All deterministic conditions met: ELIGIBLE
        return RecoveryEvaluationResult(
            is_eligible=True,
            decision="ELIGIBLE",
            reason=(
                f"Subscription is {sub_status} with verified outstanding balance of "
                f"{outstanding_balance:.2f} {currency} and {failed_payment_count} failed payment(s). "
                "Eligible for merchant-approved balance capture."
            ),
            evidence=evidence,
            policy_version=cls.POLICY_VERSION,
            suggested_action="REQUEST_MERCHANT_APPROVAL",
        )
