"""SQLAlchemy models for Recovery Engine, Approvals, Operations, AI Insights, and Audit.

Architectural Guarantees:
- Deterministic policy outputs separated from AI advisory recommendations.
- Mandatory merchant authorization records (MerchantApproval).
- Idempotent capture operations tracking unique request_id.
- Ambiguous outcome tracking requiring reconciliation before retry.
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecoveryOpportunity(Base):
    """An identified opportunity to recover eligible outstanding subscription revenue."""
    __tablename__ = "recovery_opportunities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(String(64), ForeignKey("subscriptions.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="IDENTIFIED",
        index=True,
    )  # IDENTIFIED, ELIGIBLE, PENDING_APPROVAL, APPROVED, EXECUTING, RECOVERED, REJECTED, AMBIGUOUS_RECONCILING, UNRECOVERABLE

    eligible_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    evaluations: Mapped[List["RecoveryEvaluation"]] = relationship("RecoveryEvaluation", back_populates="opportunity", cascade="all, delete-orphan")
    approvals: Mapped[List["MerchantApproval"]] = relationship("MerchantApproval", back_populates="opportunity", cascade="all, delete-orphan")
    operations: Mapped[List["RecoveryOperation"]] = relationship("RecoveryOperation", back_populates="opportunity", cascade="all, delete-orphan")
    ai_recommendations: Mapped[List["AIRecommendation"]] = relationship("AIRecommendation", back_populates="opportunity", cascade="all, delete-orphan")


class RecoveryEvaluation(Base):
    """Deterministic policy evaluation result for a recovery opportunity."""
    __tablename__ = "recovery_evaluations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_opportunities.id"), nullable=False, index=True)

    is_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decision: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # ELIGIBLE, INELIGIBLE, WAITING_NATIVE_RETRY, REQUIRES_VERIFICATION, COOLDOWN_ACTIVE

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), default="v1.0.0")
    suggested_action: Mapped[str] = mapped_column(String(128), nullable=False)

    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    opportunity: Mapped["RecoveryOpportunity"] = relationship("RecoveryOpportunity", back_populates="evaluations")


class MerchantApproval(Base):
    """Explicit human merchant authorization or rejection for recovery action."""
    __tablename__ = "merchant_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_opportunities.id"), nullable=False, index=True)

    decision: Mapped[str] = mapped_column(String(32), nullable=False)  # APPROVED, REJECTED
    merchant_user: Mapped[str] = mapped_column(String(128), default="merchant_admin")
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    opportunity: Mapped["RecoveryOpportunity"] = relationship("RecoveryOpportunity", back_populates="approvals")


class RecoveryOperation(Base):
    """Record of an executed PayPal operation (e.g. outstanding balance capture)."""
    __tablename__ = "recovery_operations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_opportunities.id"), nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    operation_type: Mapped[str] = mapped_column(String(32), default="CAPTURE")  # CAPTURE
    request_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)  # PayPal-Request-Id

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )  # INITIATED, COMPLETED, FAILED, AMBIGUOUS

    paypal_debug_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    paypal_capture_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    opportunity: Mapped["RecoveryOpportunity"] = relationship("RecoveryOpportunity", back_populates="operations")


class AIRecommendation(Base):
    """Advisory AI analysis of payment failure reason and merchant guidance."""
    __tablename__ = "ai_recommendations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_opportunities.id"), nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(String(64), nullable=False)

    failure_category: Mapped[str] = mapped_column(String(64), nullable=False)  # FUNDING, INSTRUMENT, ACCOUNT, etc.
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 to 1.0
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action_type: Mapped[str] = mapped_column(String(64), default="WAIT_FOR_RETRY")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    opportunity: Mapped["RecoveryOpportunity"] = relationship("RecoveryOpportunity", back_populates="ai_recommendations")


class AuditLog(Base):
    """Immutable audit trail of all high-value system and merchant operations."""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
