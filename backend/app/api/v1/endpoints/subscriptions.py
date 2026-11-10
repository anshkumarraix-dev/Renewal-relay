"""Subscription API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.subscription_service import SubscriptionService
from app.services.paypal_service import PayPalService
from app.schemas.subscription import SubscriptionResponse, SubscriptionDetailResponse

router = APIRouter()


def get_paypal_service(request: Request) -> PayPalService:
    """Retrieve application-managed PayPalService instance."""
    client = getattr(request.app.state, "paypal_client", None)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayPal REST client is not initialized in application state.",
        )
    return PayPalService(client)


@router.get("", response_model=List[SubscriptionResponse], summary="List tracked subscriptions")
def list_subscriptions(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieve tracked PayPal subscriptions filtered by status (e.g. ACTIVE, SUSPENDED, CANCELLED)."""
    service = SubscriptionService(db)
    return service.list_subscriptions(status=status, limit=limit)


@router.get("/{subscription_id}", response_model=SubscriptionDetailResponse, summary="Get subscription details")
def get_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve full details of a subscription including payment failures and transaction history."""
    service = SubscriptionService(db)
    sub = service.get_subscription(subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Subscription '{subscription_id}' not found.")

    return SubscriptionDetailResponse(
        id=sub.id,
        plan_id=sub.plan_id,
        merchant_id=sub.merchant_id,
        status=sub.status,
        subscriber_name=sub.subscriber_name,
        subscriber_email=sub.subscriber_email,
        outstanding_balance_amount=sub.outstanding_balance_amount,
        currency=sub.currency,
        failed_payment_count=sub.failed_payment_count,
        next_billing_time=sub.next_billing_time,
        last_payment_time=sub.last_payment_time,
        last_payment_amount=sub.last_payment_amount,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        recent_failures=sub.failures[:10] if sub.failures else [],
        recent_transactions=sub.transactions[:10] if sub.transactions else [],
    )


@router.post("/{subscription_id}/sync", response_model=SubscriptionResponse, summary="Sync subscription from PayPal")
async def sync_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
    paypal: PayPalService = Depends(get_paypal_service),
):
    """Pull authoritative subscription state from PayPal Sandbox API and synchronize internal database."""
    try:
        paypal_data = await paypal.get_subscription_details(subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch subscription from PayPal: {str(exc)}")

    service = SubscriptionService(db, paypal)
    return service.sync_subscription_from_paypal_data(paypal_data)
