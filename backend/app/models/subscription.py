"""SQLAlchemy models for Merchants, Plans, Subscriptions, Payments, and Failures.

Enforces:
- Foreign-key relationships.
- UTC timestamps.
- Explicit currency fields.
- Non-null constraints on critical business identifiers.
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    """Return current UTC timestamp with timezone awareness."""
    return datetime.now(timezone.utc)


class Merchant(Base):
    """Registered subscription merchant."""
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    paypal_payer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscriptions: Mapped[List["Subscription"]] = relationship("Subscription", back_populates="merchant")


class BillingPlan(Base):
    """Cached PayPal billing plan metadata."""
    __tablename__ = "billing_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. P-xxx
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    product_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    billing_cycles: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscriptions: Mapped[List["Subscription"]] = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    """Tracked PayPal subscription and financial renewal status."""
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. I-xxx
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("billing_plans.id"), nullable=True)
    merchant_id: Mapped[str] = mapped_column(String(64), ForeignKey("merchants.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # ACTIVE, SUSPENDED, CANCELLED, EXPIRED
    subscriber_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subscriber_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    outstanding_balance_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    failed_payment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    next_billing_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_payment_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    merchant: Mapped[Optional["Merchant"]] = relationship("Merchant", back_populates="subscriptions")
    plan: Mapped[Optional["BillingPlan"]] = relationship("BillingPlan", back_populates="subscriptions")
    failures: Mapped[List["PaymentFailure"]] = relationship("PaymentFailure", back_populates="subscription", cascade="all, delete-orphan")
    transactions: Mapped[List["PaymentTransaction"]] = relationship("PaymentTransaction", back_populates="subscription", cascade="all, delete-orphan")
    state_history: Mapped[List["SubscriptionStateHistory"]] = relationship("SubscriptionStateHistory", back_populates="subscription", cascade="all, delete-orphan")


class PaymentTransaction(Base):
    """Authoritative record of a payment, sale, or balance capture."""
    __tablename__ = "payment_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(String(64), ForeignKey("subscriptions.id"), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)  # CAPTURE, SALE, REFUND
    paypal_transaction_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # COMPLETED, PENDING, FAILED
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="transactions")


class PaymentFailure(Base):
    """Record of an individual subscription renewal failure."""
    __tablename__ = "payment_failures"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(String(64), ForeignKey("subscriptions.id"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    failure_reason_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="failures")


class SubscriptionStateHistory(Base):
    """Immutable audit trail of subscription lifecycle state transitions."""
    __tablename__ = "subscription_state_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(String(64), ForeignKey("subscriptions.id"), nullable=False, index=True)
    previous_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="WEBHOOK")  # WEBHOOK, RECONCILIATION, MERCHANT_ACTION
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="state_history")
