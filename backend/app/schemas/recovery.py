"""Pydantic schemas for Recovery Opportunities, Evaluations, Approvals, and Operations."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class RecoveryEvaluationResponse(BaseModel):
    id: str
    opportunity_id: str
    is_eligible: bool
    decision: str  # ELIGIBLE, INELIGIBLE, WAITING_NATIVE_RETRY, REQUIRES_VERIFICATION, COOLDOWN_ACTIVE
    reason: str
    evidence_json: Dict[str, Any]
    policy_version: str
    suggested_action: str
    evaluated_at: datetime

    class Config:
        from_attributes = True


class AIRecommendationResponse(BaseModel):
    id: str
    opportunity_id: str
    subscription_id: str
    failure_category: str
    confidence_score: float
    explanation: str
    evidence_json: Dict[str, Any]
    recommended_action: str
    suggested_action_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class MerchantApprovalRequest(BaseModel):
    merchant_user: str = Field(default="merchant_admin", description="Merchant reviewer identifier")
    decision_note: Optional[str] = Field(default=None, description="Optional justification or audit notes")


class MerchantApprovalResponse(BaseModel):
    id: str
    opportunity_id: str
    decision: str  # APPROVED, REJECTED
    merchant_user: str
    decision_note: Optional[str]
    decided_at: datetime

    class Config:
        from_attributes = True


class RecoveryOperationResponse(BaseModel):
    id: str
    opportunity_id: str
    subscription_id: str
    operation_type: str
    request_id: str
    amount: float
    currency: str
    status: str  # INITIATED, COMPLETED, FAILED, AMBIGUOUS
    paypal_debug_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    reconciled: bool = False
    reconciled_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecoveryOpportunityResponse(BaseModel):
    id: str
    subscription_id: str
    status: str
    eligible_amount: float
    currency: str
    detected_at: datetime
    resolved_at: Optional[datetime] = None

    subscriber_name: Optional[str] = None
    subscriber_email: Optional[str] = None
    plan_name: Optional[str] = None
    failed_payment_count: int = 0
    subscription_status: Optional[str] = None

    latest_evaluation: Optional[RecoveryEvaluationResponse] = None
    latest_ai_recommendation: Optional[AIRecommendationResponse] = None
    latest_operation: Optional[RecoveryOperationResponse] = None

    class Config:
        from_attributes = True


class ReconcileRequest(BaseModel):
    notes: Optional[str] = None


class ReconcileResponse(BaseModel):
    operation_id: str
    subscription_id: str
    previous_status: str
    reconciled_status: str
    reconciled_via: str
    paypal_debug_id: Optional[str] = None
    message: str
