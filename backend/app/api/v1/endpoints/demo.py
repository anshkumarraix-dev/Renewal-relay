"""Demo and Simulation Seeding Endpoints.

Allows merchants and reviewers to populate realistic PayPal Sandbox demo subscriptions,
renewal failures, deterministic policy evaluations, and AI advisory recommendations.

All generated records are explicitly labeled with [SIMULATED DATA].
"""

import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.subscription import Merchant, BillingPlan, Subscription, PaymentFailure, PaymentTransaction, SubscriptionStateHistory
from app.models.recovery import RecoveryOpportunity, RecoveryEvaluation, AIRecommendation, AuditLog
from app.services.recovery_policy_service import RecoveryPolicyEngine
from app.services.ai_service import AIIntelligenceService

router = APIRouter()


@router.post("/seed", summary="Seed realistic sandbox simulation data")
def seed_demo_data(db: Session = Depends(get_db)):
    """Seed realistic subscription renewal failure and recovery scenarios.

    Creates:
    - 1 Merchant and 2 Billing Plans
    - 4 realistic Subscriptions (Active with failure, Suspended with outstanding balance, Scheduled retry pending, and Recovered)
    - Realistic Payment Failures with real PayPal error codes (INSUFFICIENT_FUNDS, INSTRUMENT_DECLINED, EXPIRED_CARD)
    - Corresponding Recovery Opportunities, Deterministic Evaluations, and AI Guidance
    """
    now = datetime.now(timezone.utc)

    # 1. Merchant
    merchant = db.get(Merchant, "demo_merchant_1")
    if not merchant:
        merchant = Merchant(
            id="demo_merchant_1",
            name="CloudFlow SaaS Inc. [SIMULATED DATA]",
            email="billing@cloudflow-saas.com",
            paypal_payer_id="PAYER-DEMO-12345",
        )
        db.add(merchant)

    # 2. Billing Plans
    plan_pro = db.get(BillingPlan, "P-PRO-TIER-01")
    if not plan_pro:
        plan_pro = BillingPlan(
            id="P-PRO-TIER-01",
            name="CloudFlow Pro Annual [SIMULATED DATA]",
            description="Professional SaaS tier billed monthly",
            status="ACTIVE",
            product_id="PROD-CLOUDFLOW",
        )
        db.add(plan_pro)

    plan_ent = db.get(BillingPlan, "P-ENT-TIER-02")
    if not plan_ent:
        plan_ent = BillingPlan(
            id="P-ENT-TIER-02",
            name="CloudFlow Enterprise [SIMULATED DATA]",
            description="Enterprise tier with priority SLA",
            status="ACTIVE",
            product_id="PROD-CLOUDFLOW",
        )
        db.add(plan_ent)

    db.commit()

    # 3. Subscriptions
    # Scenario A: Eligible Suspended Subscription (Insufficient Funds)
    sub_a_id = "I-DEMO-SUB-001"
    sub_a = db.get(Subscription, sub_a_id)
    if not sub_a:
        sub_a = Subscription(
            id=sub_a_id,
            plan_id="P-PRO-TIER-01",
            merchant_id="demo_merchant_1",
            status="SUSPENDED",
            subscriber_name="Sarah Jenkins [SIMULATED]",
            subscriber_email="sarah.jenkins@example.com",
            outstanding_balance_amount=89.00,
            currency="USD",
            failed_payment_count=2,
            next_billing_time=None,  # No native retry scheduled
            last_payment_time=now - timedelta(days=35),
            last_payment_amount=89.00,
        )
        db.add(sub_a)

        # Payment failure
        fail_a = PaymentFailure(
            id=str(uuid.uuid4()),
            subscription_id=sub_a_id,
            amount=89.00,
            currency="USD",
            failure_reason_code="INSUFFICIENT_FUNDS",
            failure_message="Payment declined due to insufficient buyer account balance.",
            occurred_at=now - timedelta(days=2),
        )
        db.add(fail_a)

        # Opportunity
        opp_a = RecoveryOpportunity(
            id=str(uuid.uuid4()),
            subscription_id=sub_a_id,
            status="ELIGIBLE",
            eligible_amount=89.00,
            currency="USD",
            detected_at=now - timedelta(days=2),
        )
        db.add(opp_a)

        # Evaluation
        eval_a = RecoveryEvaluation(
            id=str(uuid.uuid4()),
            opportunity_id=opp_a.id,
            is_eligible=True,
            decision="ELIGIBLE",
            reason="Subscription is SUSPENDED with verified outstanding balance of 89.00 USD and 2 failed payment(s). Eligible for merchant-approved balance capture.",
            evidence_json={
                "subscription_status": "SUSPENDED",
                "outstanding_balance": 89.0,
                "currency": "USD",
                "failed_payment_count": 2,
            },
            policy_version="v1.0.0",
            suggested_action="REQUEST_MERCHANT_APPROVAL",
        )
        db.add(eval_a)

        # AI Recommendation
        ai_a = AIRecommendation(
            id=str(uuid.uuid4()),
            opportunity_id=opp_a.id,
            subscription_id=sub_a_id,
            failure_category="FUNDING_FAILURE",
            confidence_score=0.92,
            explanation="The customer's bank account had insufficient funds during scheduled renewal. The subscriber has confirmed updated funds.",
            evidence_json={"points": ["Status: SUSPENDED", "Decline: INSUFFICIENT_FUNDS", "Failed attempts: 2"]},
            recommended_action="Outstanding balance of 89.00 USD can be captured directly via merchant-approved recovery capture.",
            suggested_action_type="CAPTURE_BALANCE",
        )
        db.add(ai_a)

    # Scenario B: Eligible Active Subscription (Expired Card)
    sub_b_id = "I-DEMO-SUB-002"
    sub_b = db.get(Subscription, sub_b_id)
    if not sub_b:
        sub_b = Subscription(
            id=sub_b_id,
            plan_id="P-PRO-TIER-01",
            merchant_id="demo_merchant_1",
            status="ACTIVE",
            subscriber_name="Marcus Vance [SIMULATED]",
            subscriber_email="marcus.v@example.org",
            outstanding_balance_amount=49.00,
            currency="USD",
            failed_payment_count=1,
            next_billing_time=None,
            last_payment_time=now - timedelta(days=32),
            last_payment_amount=49.00,
        )
        db.add(sub_b)

        fail_b = PaymentFailure(
            id=str(uuid.uuid4()),
            subscription_id=sub_b_id,
            amount=49.00,
            currency="USD",
            failure_reason_code="INSTRUMENT_DECLINED",
            failure_message="Card issuer declined transaction. Card expiration date reached.",
            occurred_at=now - timedelta(days=1),
        )
        db.add(fail_b)

        opp_b = RecoveryOpportunity(
            id=str(uuid.uuid4()),
            subscription_id=sub_b_id,
            status="ELIGIBLE",
            eligible_amount=49.00,
            currency="USD",
            detected_at=now - timedelta(days=1),
        )
        db.add(opp_b)

        eval_b = RecoveryEvaluation(
            id=str(uuid.uuid4()),
            opportunity_id=opp_b.id,
            is_eligible=True,
            decision="ELIGIBLE",
            reason="Subscription is ACTIVE with verified outstanding balance of 49.00 USD and 1 failed payment(s). Eligible for merchant-approved balance capture.",
            evidence_json={"subscription_status": "ACTIVE", "outstanding_balance": 49.0, "currency": "USD"},
            policy_version="v1.0.0",
            suggested_action="REQUEST_MERCHANT_APPROVAL",
        )
        db.add(eval_b)

        ai_b = AIRecommendation(
            id=str(uuid.uuid4()),
            opportunity_id=opp_b.id,
            subscription_id=sub_b_id,
            failure_category="INSTRUMENT_EXPIRED_OR_INVALID",
            confidence_score=0.88,
            explanation="The payment card was declined by the issuer because the expiration date was reached.",
            evidence_json={"points": ["Status: ACTIVE", "Decline: INSTRUMENT_DECLINED", "Card expired"]},
            recommended_action="Customer has updated wallet details. Ready for merchant authorization.",
            suggested_action_type="CAPTURE_BALANCE",
        )
        db.add(ai_b)

    # Scenario C: Ineligible Subscription - Waiting Native PayPal Retry
    sub_c_id = "I-DEMO-SUB-003"
    sub_c = db.get(Subscription, sub_c_id)
    if not sub_c:
        sub_c = Subscription(
            id=sub_c_id,
            plan_id="P-ENT-TIER-02",
            merchant_id="demo_merchant_1",
            status="ACTIVE",
            subscriber_name="Elena Rostova [SIMULATED]",
            subscriber_email="elena.r@enterprise-corp.com",
            outstanding_balance_amount=249.00,
            currency="USD",
            failed_payment_count=1,
            next_billing_time=now + timedelta(days=2),  # Scheduled PayPal native retry in 2 days!
            last_payment_time=now - timedelta(days=30),
            last_payment_amount=249.00,
        )
        db.add(sub_c)

        opp_c = RecoveryOpportunity(
            id=str(uuid.uuid4()),
            subscription_id=sub_c_id,
            status="IDENTIFIED",
            eligible_amount=249.00,
            currency="USD",
            detected_at=now - timedelta(hours=12),
        )
        db.add(opp_c)

        eval_c = RecoveryEvaluation(
            id=str(uuid.uuid4()),
            opportunity_id=opp_c.id,
            is_eligible=False,
            decision="WAITING_NATIVE_RETRY",
            reason=f"PayPal has scheduled a native automated renewal retry on {(now + timedelta(days=2)).strftime('%Y-%m-%d %H:%M UTC')}. Awaiting native retry outcome before merchant intervention.",
            evidence_json={"subscription_status": "ACTIVE", "next_billing_time": (now + timedelta(days=2)).isoformat()},
            policy_version="v1.0.0",
            suggested_action="AWAIT_NATIVE_RETRY",
        )
        db.add(eval_c)

        ai_c = AIRecommendation(
            id=str(uuid.uuid4()),
            opportunity_id=opp_c.id,
            subscription_id=sub_c_id,
            failure_category="FUNDING_FAILURE",
            confidence_score=0.85,
            explanation="Initial renewal attempt failed. PayPal automated retry engine will attempt secondary capture in 48 hours.",
            evidence_json={"points": ["Next retry scheduled by PayPal", "Do not double-charge customer"]},
            recommended_action="Wait for PayPal scheduled retry before taking merchant recovery action.",
            suggested_action_type="WAIT_FOR_RETRY",
        )
        db.add(ai_c)

    # Scenario D: Already Recovered Subscription
    sub_d_id = "I-DEMO-SUB-004"
    sub_d = db.get(Subscription, sub_d_id)
    if not sub_d:
        sub_d = Subscription(
            id=sub_d_id,
            plan_id="P-PRO-TIER-01",
            merchant_id="demo_merchant_1",
            status="ACTIVE",
            subscriber_name="David Chen [SIMULATED]",
            subscriber_email="david.chen@technova.io",
            outstanding_balance_amount=0.0,
            currency="USD",
            failed_payment_count=0,
            last_payment_time=now - timedelta(days=1),
            last_payment_amount=89.00,
        )
        db.add(sub_d)

        # Recorded recovered transaction
        tx_d = PaymentTransaction(
            id=str(uuid.uuid4()),
            subscription_id=sub_d_id,
            transaction_type="CAPTURE",
            paypal_transaction_id="CAP-RECOVERED-9921",
            amount=89.00,
            currency="USD",
            status="COMPLETED",
            timestamp=now - timedelta(days=1),
        )
        db.add(tx_d)

        opp_d = RecoveryOpportunity(
            id=str(uuid.uuid4()),
            subscription_id=sub_d_id,
            status="RECOVERED",
            eligible_amount=89.00,
            currency="USD",
            detected_at=now - timedelta(days=4),
            resolved_at=now - timedelta(days=1),
        )
        db.add(opp_d)

    db.commit()
    return {
        "status": "success",
        "message": "Successfully seeded realistic PayPal Sandbox demonstration data [SIMULATED DATA].",
        "seeded_subscriptions": [sub_a_id, sub_b_id, sub_c_id, sub_d_id],
    }
