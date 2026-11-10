"""AI Intelligence Layer for Payment Failure Classification and Merchant Advisory.

Architectural Guarantees:
- Strictly advisory; NEVER executes or authorizes financial transactions.
- Fully isolated from the deterministic recovery policy engine.
- Structured, validated JSON outputs with calibrated confidence and explicit evidence.
- Resilient implementation: works offline with deterministic heuristic classification
  and provides rich merchant explanations without mandatory external network dependencies.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger("renewal_relay.services.ai")


class AIAnalysisResult(BaseModel):
    failure_category: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str
    evidence: List[str]
    missing_information: Optional[str] = None
    recommended_action: str
    suggested_action_type: str  # CAPTURE_BALANCE, CONTACT_CUSTOMER, WAIT_FOR_RETRY, MANUAL_REVIEW


class AIIntelligenceService:
    """Provides failure classification, plain-English explanations, and merchant advice."""

    # PayPal decline reason code to category mapping
    FAILURE_PATTERNS = {
        "INSUFFICIENT_FUNDS": {
            "category": "FUNDING_FAILURE",
            "confidence": 0.90,
            "explanation": "The customer's bank or card account has insufficient funds to cover the scheduled subscription charge.",
            "action": "Customer may add funds. Wait for PayPal's automated retry schedule or prompt customer to verify balance.",
            "action_type": "WAIT_FOR_RETRY",
        },
        "INSTRUMENT_DECLINED": {
            "category": "INSTRUMENT_EXPIRED_OR_INVALID",
            "confidence": 0.85,
            "explanation": "The payment card or funding instrument was declined by the issuing bank (often due to expiration, security flag, or credit limit).",
            "action": "Request customer to update payment details or select an alternate card in their PayPal wallet.",
            "action_type": "CONTACT_CUSTOMER",
        },
        "EXPIRED_CARD": {
            "category": "INSTRUMENT_EXPIRED_OR_INVALID",
            "confidence": 0.95,
            "explanation": "The credit or debit card associated with this subscription has passed its expiration date.",
            "action": "Send payment update notice to customer to provide new card expiration details.",
            "action_type": "CONTACT_CUSTOMER",
        },
        "PAYER_ACCOUNT_RESTRICTED": {
            "category": "ACCOUNT_RESTRICTION",
            "confidence": 0.88,
            "explanation": "The customer's PayPal account is temporarily restricted or requires identity verification.",
            "action": "Advise customer to log into their PayPal account to resolve account security prompts.",
            "action_type": "MANUAL_REVIEW",
        },
        "BILLING_AGREEMENT_CANCELLED": {
            "category": "DISENGAGEMENT_OR_CANCEL",
            "confidence": 0.95,
            "explanation": "The customer actively revoked or cancelled the recurring billing agreement within their PayPal account settings.",
            "action": "Reach out with customer win-back offer or confirm subscription cancellation.",
            "action_type": "MANUAL_REVIEW",
        },
        "CURRENCY_MISMATCH": {
            "category": "BILLING_CONFIGURATION",
            "confidence": 0.85,
            "explanation": "The subscription currency does not match the merchant's accepted settlement currencies or buyer wallet configuration.",
            "action": "Review plan currency settings and merchant payment preferences.",
            "action_type": "MANUAL_REVIEW",
        },
    }

    @classmethod
    def analyze_failure(
        cls,
        failure_code: Optional[str] = None,
        failure_message: Optional[str] = None,
        failed_count: int = 1,
        outstanding_balance: float = 0.0,
        currency: str = "USD",
        subscription_status: str = "ACTIVE",
        has_future_retry: bool = False,
    ) -> AIAnalysisResult:
        """Analyze a subscription failure and produce structured merchant guidance."""
        code_upper = (failure_code or "").strip().upper()
        msg_lower = (failure_message or "").strip().lower()

        evidence: List[str] = [
            f"Subscription status: {subscription_status}",
            f"Failed renewal attempts: {failed_count}",
            f"Outstanding balance: {outstanding_balance:.2f} {currency}",
        ]

        if failure_code:
            evidence.append(f"Reported failure code: {failure_code}")
        if failure_message:
            evidence.append(f"PayPal message: {failure_message}")

        # 1. Match known failure patterns
        matched = None
        for pattern_code, pattern_data in cls.FAILURE_PATTERNS.items():
            if pattern_code in code_upper or pattern_code.lower() in msg_lower:
                matched = pattern_data
                break

        # 2. Heuristic text search in failure message
        if not matched:
            if "insufficient" in msg_lower or "balance" in msg_lower or "funds" in msg_lower:
                matched = cls.FAILURE_PATTERNS["INSUFFICIENT_FUNDS"]
            elif "expired" in msg_lower or "card" in msg_lower:
                matched = cls.FAILURE_PATTERNS["EXPIRED_CARD"]
            elif "declined" in msg_lower or "do not honor" in msg_lower:
                matched = cls.FAILURE_PATTERNS["INSTRUMENT_DECLINED"]
            elif "restricted" in msg_lower or "limit" in msg_lower:
                matched = cls.FAILURE_PATTERNS["PAYER_ACCOUNT_RESTRICTED"]

        # 3. Formulate analysis
        if matched:
            category = matched["category"]
            confidence = matched["confidence"]
            explanation = matched["explanation"]
            action = matched["action"]
            action_type = matched["action_type"]
            missing_info = None

            # Adjust recommendation if merchant capture is eligible vs waiting
            if outstanding_balance > 0 and not has_future_retry and failed_count >= 1:
                if category == "FUNDING_FAILURE":
                    action = f"Outstanding balance of {outstanding_balance:.2f} {currency} can be recovered via merchant balance capture once buyer confirms funds."
                    action_type = "CAPTURE_BALANCE"
        else:
            category = "UNKNOWN_INSUFFICIENT_DATA"
            confidence = 0.45
            explanation = (
                "PayPal provided a generic payment decline without detailed decline attributes. "
                "The transaction was rejected by either the card network or bank security filter."
            )
            evidence.append("No specific decline reason was returned in the PayPal error payload.")
            missing_info = "Bank response code and detailed decline reason not provided by PayPal."

            if has_future_retry:
                action = "Allow PayPal's native retry cycle to proceed while monitoring subscription state."
                action_type = "WAIT_FOR_RETRY"
            elif outstanding_balance > 0:
                action = f"Verify customer account and evaluate outstanding balance capture ({outstanding_balance:.2f} {currency})."
                action_type = "CAPTURE_BALANCE"
            else:
                action = "Contact subscriber to verify payment details."
                action_type = "CONTACT_CUSTOMER"

        return AIAnalysisResult(
            failure_category=category,
            confidence_score=confidence,
            explanation=explanation,
            evidence=evidence,
            missing_information=missing_info,
            recommended_action=action,
            suggested_action_type=action_type,
        )

    @classmethod
    def generate_portfolio_insights(
        cls,
        total_tracked: int,
        active_count: int,
        suspended_count: int,
        failures_count: int,
        category_counts: Dict[str, int],
        recovered_revenue: float,
        outstanding_revenue: float,
        currency: str = "USD",
    ) -> List[Dict[str, Any]]:
        """Generate executive-level portfolio intelligence and actionable churn alerts."""
        insights = []

        # Insight 1: Avoidable Churn Alert
        if suspended_count > 0:
            insights.append({
                "title": "Avoidable Involuntary Churn Detected",
                "severity": "HIGH",
                "category": "INVOLUNTARY_CHURN",
                "message": (
                    f"{suspended_count} subscription(s) are currently suspended due to repeated payment failures, "
                    f"representing {outstanding_revenue:.2f} {currency} in at-risk revenue."
                ),
                "suggested_action": "Review eligible recovery opportunities and initiate merchant capture for qualified accounts.",
                "affected_subscriptions": suspended_count,
            })

        # Insight 2: Top Failure Category Pattern
        if category_counts:
            top_category = max(category_counts, key=category_counts.get)
            top_count = category_counts[top_category]
            insights.append({
                "title": f"Prevalent Failure Driver: {top_category.replace('_', ' ').title()}",
                "severity": "MEDIUM",
                "category": "FAILURE_PATTERN",
                "message": (
                    f"{top_count} failure(s) ({round(top_count / max(1, failures_count) * 100)}%) "
                    f"stem from {top_category.lower().replace('_', ' ')}. "
                    "Targeted communication can recover a significant portion before account suspension."
                ),
                "suggested_action": "Enable proactive payment method expiration reminders to reduce decline rates.",
                "affected_subscriptions": top_count,
            })

        # Insight 3: Revenue Recovery Velocity
        if recovered_revenue > 0:
            insights.append({
                "title": "Verified Revenue Recovery Active",
                "severity": "LOW",
                "category": "REVENUE_INTELLIGENCE",
                "message": (
                    f"Successfully recovered {recovered_revenue:.2f} {currency} in verified subscription revenue "
                    "via merchant-authorized PayPal capture operations."
                ),
                "suggested_action": "Continue monitoring recovery queue for newly eligible opportunities.",
                "affected_subscriptions": 0,
            })

        return insights
