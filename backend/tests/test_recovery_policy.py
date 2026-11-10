"""Unit tests for the Deterministic Recovery Policy Engine (P4).

Architectural Guarantees:
- Fully separated from AI logic.
- Pure deterministic outputs: exact same input guarantees exact same decision.
- Zero blind approvals.
"""

import unittest
from datetime import datetime, timezone, timedelta

from app.services.recovery_policy_service import RecoveryPolicyEngine


class TestRecoveryPolicyEngine(unittest.TestCase):
    """Test deterministic evaluation rules."""

    def setUp(self):
        self.now = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_eligible_suspended_subscription(self):
        """Active/Suspended subscription with balance > 0 and failed payment >= 1 is ELIGIBLE."""
        res = RecoveryPolicyEngine.evaluate(
            subscription_status="SUSPENDED",
            outstanding_balance=89.00,
            currency="USD",
            failed_payment_count=2,
            next_billing_time=None,
            current_time=self.now,
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.decision, "ELIGIBLE")
        self.assertEqual(res.suggested_action, "REQUEST_MERCHANT_APPROVAL")
        self.assertIn("SUSPENDED", res.reason)

    def test_eligible_active_subscription(self):
        """Active subscription with outstanding balance and failed count >= 1 is ELIGIBLE."""
        res = RecoveryPolicyEngine.evaluate(
            subscription_status="ACTIVE",
            outstanding_balance=49.00,
            currency="USD",
            failed_payment_count=1,
            next_billing_time=None,
            current_time=self.now,
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.decision, "ELIGIBLE")

    def test_ineligible_cancelled_subscription(self):
        """Cancelled or expired subscriptions are strictly INELIGIBLE."""
        for bad_status in ("CANCELLED", "EXPIRED", "APPROVAL_PENDING"):
            res = RecoveryPolicyEngine.evaluate(
                subscription_status=bad_status,
                outstanding_balance=50.00,
                currency="USD",
                failed_payment_count=1,
                current_time=self.now,
            )
            self.assertFalse(res.is_eligible)
            self.assertEqual(res.decision, "INELIGIBLE")

    def test_ineligible_zero_outstanding_balance(self):
        """Subscriptions with 0.00 balance cannot be captured."""
        res = RecoveryPolicyEngine.evaluate(
            subscription_status="ACTIVE",
            outstanding_balance=0.00,
            currency="USD",
            failed_payment_count=1,
            current_time=self.now,
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.decision, "INELIGIBLE")
        self.assertIn("below minimum", res.reason)

    def test_ineligible_zero_failed_payments(self):
        """Subscriptions with no failed payments require no recovery."""
        res = RecoveryPolicyEngine.evaluate(
            subscription_status="ACTIVE",
            outstanding_balance=50.00,
            currency="USD",
            failed_payment_count=0,
            current_time=self.now,
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.decision, "INELIGIBLE")
        self.assertIn("no recorded failed payment", res.reason)

    def test_waiting_native_paypal_retry(self):
        """If PayPal has scheduled an automated retry within 5 days, wait for native retry."""
        retry_time = self.now + timedelta(days=2)
        res = RecoveryPolicyEngine.evaluate(
            subscription_status="ACTIVE",
            outstanding_balance=100.00,
            currency="USD",
            failed_payment_count=1,
            next_billing_time=retry_time,
            current_time=self.now,
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.decision, "WAITING_NATIVE_RETRY")
        self.assertEqual(res.suggested_action, "AWAIT_NATIVE_RETRY")

    def test_in_flight_ambiguous_operation_blocks_subsequent_capture(self):
        """Existing INITIATED or AMBIGUOUS operations must block duplicate capture."""
        for pending_status in ("INITIATED", "AMBIGUOUS"):
            res = RecoveryPolicyEngine.evaluate(
                subscription_status="SUSPENDED",
                outstanding_balance=100.00,
                currency="USD",
                failed_payment_count=1,
                last_operation_status=pending_status,
                current_time=self.now,
            )
            self.assertFalse(res.is_eligible)
            self.assertEqual(res.decision, "REQUIRES_VERIFICATION")
            self.assertEqual(res.suggested_action, "RECONCILE_PREVIOUS_OPERATION")

    def test_cooldown_period_enforced(self):
        """Attempts less than 24 hours apart are blocked by cooldown."""
        last_op_time = self.now - timedelta(hours=6)
        res = RecoveryPolicyEngine.evaluate(
            subscription_status="SUSPENDED",
            outstanding_balance=100.00,
            currency="USD",
            failed_payment_count=1,
            last_operation_status="FAILED",
            last_operation_time=last_op_time,
            current_time=self.now,
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.decision, "COOLDOWN_ACTIVE")
        self.assertIn("cooldown active", res.reason.lower())


if __name__ == "__main__":
    unittest.main()
