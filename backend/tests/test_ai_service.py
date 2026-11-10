"""Unit tests for the AI Intelligence Layer (P5).

Architectural Guarantees:
- AI is strictly advisory; outputs structured, validated JSON.
- Evaluates failure reason codes and provides calibrated confidence.
- Generates evidence lists and flags missing information.
"""

import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai_service import AIIntelligenceService


class TestAIService(unittest.TestCase):
    """Test AI advisory failure classification and explanation."""

    def test_insufficient_funds_classification(self):
        """Verify INSUFFICIENT_FUNDS maps to FUNDING_FAILURE with high confidence."""
        res = AIIntelligenceService.analyze_failure(
            failure_code="INSUFFICIENT_FUNDS",
            failure_message="Buyer bank declined charge: not enough funds",
            failed_count=2,
            outstanding_balance=89.00,
            currency="USD",
            subscription_status="SUSPENDED",
        )
        self.assertEqual(res.failure_category, "FUNDING_FAILURE")
        self.assertGreaterEqual(res.confidence_score, 0.85)
        self.assertIn("insufficient funds", res.explanation.lower())
        self.assertTrue(len(res.evidence) >= 3)

    def test_instrument_declined_classification(self):
        """Verify INSTRUMENT_DECLINED maps to INSTRUMENT_EXPIRED_OR_INVALID."""
        res = AIIntelligenceService.analyze_failure(
            failure_code="INSTRUMENT_DECLINED",
            failure_message="Card issuer rejected the charge",
            failed_count=1,
            outstanding_balance=49.00,
            currency="USD",
        )
        self.assertEqual(res.failure_category, "INSTRUMENT_EXPIRED_OR_INVALID")
        self.assertGreaterEqual(res.confidence_score, 0.80)
        self.assertEqual(res.suggested_action_type, "CONTACT_CUSTOMER")

    def test_expired_card_classification(self):
        """Verify EXPIRED_CARD maps to INSTRUMENT_EXPIRED_OR_INVALID."""
        res = AIIntelligenceService.analyze_failure(
            failure_code="EXPIRED_CARD",
            failure_message="Card expiration date has passed",
            failed_count=1,
            outstanding_balance=29.00,
        )
        self.assertEqual(res.failure_category, "INSTRUMENT_EXPIRED_OR_INVALID")
        self.assertGreaterEqual(res.confidence_score, 0.90)

    def test_unknown_decline_fallback(self):
        """Unrecognized decline code falls back safely to UNKNOWN_INSUFFICIENT_DATA with lower confidence."""
        res = AIIntelligenceService.analyze_failure(
            failure_code="GENERAL_FAILURE_999",
            failure_message="Transaction could not be completed",
            failed_count=1,
            outstanding_balance=50.00,
        )
        self.assertEqual(res.failure_category, "UNKNOWN_INSUFFICIENT_DATA")
        self.assertLessEqual(res.confidence_score, 0.50)
        self.assertIsNotNone(res.missing_information)
        self.assertIn("not provided by PayPal", res.missing_information)

    def test_portfolio_insights_generation(self):
        """Verify portfolio-level alert and avoidable churn detection."""
        insights = AIIntelligenceService.generate_portfolio_insights(
            total_tracked=20,
            active_count=15,
            suspended_count=5,
            failures_count=8,
            category_counts={"FUNDING_FAILURE": 5, "INSTRUMENT_EXPIRED_OR_INVALID": 3},
            recovered_revenue=350.00,
            outstanding_revenue=445.00,
            currency="USD",
        )
        self.assertTrue(len(insights) >= 2)
        churn_alert = next((item for item in insights if item["category"] == "INVOLUNTARY_CHURN"), None)
        self.assertIsNotNone(churn_alert)
        self.assertEqual(churn_alert["severity"], "HIGH")
        self.assertIn("5 subscription(s) are currently suspended", churn_alert["message"])


if __name__ == "__main__":
    unittest.main()
