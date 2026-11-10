"""SQLAlchemy models for PayPal Webhook Events and Ingestion Logs.

Ensures:
- Event ID deduplication (unique index on paypal_event_id).
- Raw request payload preservation.
- Cryptographic verification tracking.
- Idempotent and replay-safe processing.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WebhookEvent(Base):
    """Authoritative record of received PayPal webhook events."""
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    paypal_event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    verification_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED", index=True)  # VERIFIED, UNVERIFIED, REJECTED, SIMULATED
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
