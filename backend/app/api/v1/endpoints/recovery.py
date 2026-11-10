"""Recovery Opportunities, Policy Evaluation, Approvals, and Capture Execution Endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.services.recovery_service import RecoveryService
from app.services.paypal_service import PayPalService
from app.services.subscription_service import SubscriptionService
from app.models.recovery import RecoveryOpportunity, RecoveryOperation
from app.models.subscription import Subscription
from app.schemas.recovery import (
    RecoveryOpportunityResponse,
    RecoveryEvaluationResponse,
    MerchantApprovalRequest,
    RecoveryOperationResponse,
    ReconcileRequest,
    ReconcileResponse,
)

router = APIRouter()


def get_paypal_service(request: Request) -> PayPalService:
    client = getattr(request.app.state, "paypal_client", None)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayPal REST client is not initialized in application state.",
        )
    return PayPalService(client)


def _format_opportunity_response(opp: RecoveryOpportunity, db: Session) -> RecoveryOpportunityResponse:
    sub = db.get(Subscription, opp.subscription_id)
    plan_name = sub.plan.name if sub and sub.plan else None

    # Get latest evaluation, AI recommendation, and operation
    latest_eval = opp.evaluations[-1] if opp.evaluations else None
    latest_ai = opp.ai_recommendations[-1] if opp.ai_recommendations else None
    latest_op = opp.operations[-1] if opp.operations else None

    return RecoveryOpportunityResponse(
        id=opp.id,
        subscription_id=opp.subscription_id,
        status=opp.status,
        eligible_amount=opp.eligible_amount,
        currency=opp.currency,
        detected_at=opp.detected_at,
        resolved_at=opp.resolved_at,
        subscriber_name=sub.subscriber_name if sub else None,
        subscriber_email=sub.subscriber_email if sub else None,
        plan_name=plan_name,
        failed_payment_count=sub.failed_payment_count if sub else 0,
        subscription_status=sub.status if sub else None,
        latest_evaluation=RecoveryEvaluationResponse.model_validate(latest_eval) if latest_eval else None,
        latest_ai_recommendation=latest_ai,
        latest_operation=RecoveryOperationResponse.model_validate(latest_op) if latest_op else None,
    )


@router.get("/opportunities", response_model=List[RecoveryOpportunityResponse], summary="List recovery opportunities")
def list_opportunities(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieve recovery opportunities sorted by detection date with policy evaluation and AI advice."""
    service = RecoveryService(db)
    opps = service.list_opportunities(status=status, limit=limit)
    return [_format_opportunity_response(opp, db) for opp in opps]


@router.get("/opportunities/{opportunity_id}", response_model=RecoveryOpportunityResponse, summary="Get recovery opportunity")
def get_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve details for a single recovery opportunity."""
    service = RecoveryService(db)
    opp = service.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail=f"Recovery opportunity '{opportunity_id}' not found.")
    return _format_opportunity_response(opp, db)


@router.post("/opportunities/{opportunity_id}/evaluate", response_model=RecoveryOpportunityResponse, summary="Evaluate recovery eligibility")
def evaluate_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
    paypal: PayPalService = Depends(get_paypal_service),
):
    """Execute deterministic policy engine evaluation on a recovery opportunity."""
    service = RecoveryService(db, paypal)
    opp = service.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail=f"Recovery opportunity '{opportunity_id}' not found.")

    sub = db.get(Subscription, opp.subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Underlying subscription not found.")

    sub_service = SubscriptionService(db, paypal)
    opp = sub_service.ensure_recovery_opportunity(sub)
    return _format_opportunity_response(opp, db)


@router.post("/opportunities/{opportunity_id}/approve", response_model=RecoveryOpportunityResponse, summary="Approve recovery capture")
async def approve_recovery(
    opportunity_id: str,
    payload: MerchantApprovalRequest,
    db: Session = Depends(get_db),
    paypal: PayPalService = Depends(get_paypal_service),
):
    """Explicit merchant authorization to execute outstanding balance capture against PayPal Sandbox.

    Guarantees:
    - Pre-execution deterministic policy re-evaluation.
    - Mandatory merchant authorization audit record.
    - Unique idempotency key pinned to PayPal-Request-Id.
    - Ambiguous outcomes trigger reconciliation; ZERO blind retries.
    """
    service = RecoveryService(db, paypal)
    try:
        opp = await service.approve_recovery(
            opportunity_id=opportunity_id,
            merchant_user=payload.merchant_user,
            note=payload.decision_note,
        )
        return _format_opportunity_response(opp, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Capture execution failed: {str(exc)}")


@router.post("/opportunities/{opportunity_id}/reject", response_model=RecoveryOpportunityResponse, summary="Reject recovery opportunity")
async def reject_recovery(
    opportunity_id: str,
    payload: MerchantApprovalRequest,
    db: Session = Depends(get_db),
    paypal: PayPalService = Depends(get_paypal_service),
):
    """Record explicit merchant dismissal or rejection of a recovery opportunity."""
    service = RecoveryService(db, paypal)
    try:
        opp = await service.reject_recovery(
            opportunity_id=opportunity_id,
            merchant_user=payload.merchant_user,
            note=payload.decision_note,
        )
        return _format_opportunity_response(opp, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/operations/{operation_id}/reconcile", response_model=ReconcileResponse, summary="Reconcile ambiguous operation")
async def reconcile_operation(
    operation_id: str,
    payload: Optional[ReconcileRequest] = None,
    db: Session = Depends(get_db),
    paypal: PayPalService = Depends(get_paypal_service),
):
    """Reconcile an ambiguous recovery operation against authoritative PayPal subscription transaction history."""
    service = RecoveryService(db, paypal)
    try:
        notes = payload.notes if payload else None
        result = await service.reconcile_operation(operation_id=operation_id, notes=notes)
        return ReconcileResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reconciliation error: {str(exc)}")
