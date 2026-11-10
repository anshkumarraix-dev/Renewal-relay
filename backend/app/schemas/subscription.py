"""Pydantic schemas for subscriptions, plans, failures, and transactions."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class BillingPlanBase(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str = "ACTIVE"
    product_id: Optional[str] = None
    billing_cycles: Optional[Dict[str, Any]] = None


class BillingPlanResponse(BillingPlanBase):
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentFailureResponse(BaseModel):
    id: str
    subscription_id: str
    amount: float
    currency: str
    failure_reason_code: Optional[str] = None
    failure_message: Optional[str] = None
    occurred_at: datetime

    class Config:
        from_attributes = True


class PaymentTransactionResponse(BaseModel):
    id: str
    subscription_id: str
    transaction_type: str
    paypal_transaction_id: Optional[str] = None
    amount: float
    currency: str
    status: str
    timestamp: datetime

    class Config:
        from_attributes = True


class SubscriptionBase(BaseModel):
    id: str
    plan_id: Optional[str] = None
    merchant_id: Optional[str] = None
    status: str
    subscriber_name: Optional[str] = None
    subscriber_email: Optional[str] = None
    outstanding_balance_amount: float = 0.0
    currency: str = "USD"
    failed_payment_count: int = 0
    next_billing_time: Optional[datetime] = None
    last_payment_time: Optional[datetime] = None
    last_payment_amount: Optional[float] = None


class SubscriptionResponse(SubscriptionBase):
    created_at: datetime
    updated_at: datetime
    plan: Optional[BillingPlanResponse] = None

    class Config:
        from_attributes = True


class SubscriptionDetailResponse(SubscriptionResponse):
    recent_failures: List[PaymentFailureResponse] = []
    recent_transactions: List[PaymentTransactionResponse] = []
