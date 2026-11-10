"""Pydantic schemas for Webhook Ingestion and Verification."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class WebhookIngestResponse(BaseModel):
    status: str  # "received", "already_processed", "ignored", "error"
    event_id: str
    event_type: str
    message: str


class WebhookEventResponse(BaseModel):
    id: str
    paypal_event_id: str
    event_type: str
    resource_type: str
    summary: Optional[str] = None
    verification_status: str
    processed: bool
    error_message: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
