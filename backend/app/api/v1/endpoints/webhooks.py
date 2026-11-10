"""PayPal Webhook Endpoints."""

import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, Response, status, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.core.database import get_db
from app.services.webhook_service import WebhookService
from app.services.paypal_service import PayPalService
from app.models.webhook import WebhookEvent
from app.schemas.webhook import WebhookIngestResponse, WebhookEventResponse

router = APIRouter()


def get_paypal_service(request: Request) -> Optional[PayPalService]:
    client = getattr(request.app.state, "paypal_client", None)
    return PayPalService(client) if client else None


@router.post("/paypal", response_model=WebhookIngestResponse, summary="Ingest PayPal webhook event")
async def handle_paypal_webhook(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    paypal: Optional[PayPalService] = Depends(get_paypal_service),
):
    """Receive and verify an inbound PayPal webhook event.

    - Preserves raw body bytes for cryptographic signature verification.
    - Verifies PayPal signature against /v1/notifications/verify-webhook-signature.
    - Deduplicates event ID (idempotent 200 OK on replays).
    - Dispatches to internal subscription and recovery handlers.
    """
    raw_body = await request.body()
    try:
        event_json = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(exc)}")

    service = WebhookService(db, paypal)
    status_result, event_id, message = await service.ingest_event(
        headers=dict(request.headers),
        raw_body_bytes=raw_body,
        event_json=event_json,
    )

    if status_result == "signature_failed":
        response.status_code = status.HTTP_400_BAD_REQUEST
    elif status_result == "error":
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        response.status_code = status.HTTP_200_OK

    return WebhookIngestResponse(
        status=status_result,
        event_id=event_id,
        event_type=event_json.get("event_type", "UNKNOWN"),
        message=message,
    )


@router.get("/events", response_model=List[WebhookEventResponse], summary="List received webhook events")
def list_webhook_events(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieve audit history of received PayPal webhook events and verification outcomes."""
    stmt = select(WebhookEvent).order_by(desc(WebhookEvent.created_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())
