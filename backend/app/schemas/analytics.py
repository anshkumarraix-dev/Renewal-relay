"""Pydantic schemas for Executive Dashboard and Revenue Intelligence."""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class OverviewMetrics(BaseModel):
    total_subscriptions: int
    active_subscriptions: int
    suspended_subscriptions: int
    failed_renewals_count: int
    eligible_recovery_opportunities: int
    pending_approvals: int
    verified_recovered_revenue: float
    outstanding_eligible_revenue: float
    currency: str = "USD"


class RevenueMetrics(BaseModel):
    verified_recovered_revenue: float
    outstanding_eligible_revenue: float
    total_failed_revenue: float
    recovery_rate_percentage: float
    currency: str = "USD"
    revenue_by_month: List[Dict[str, Any]] = []


class RecoveryMetrics(BaseModel):
    total_attempts: int
    successful_recoveries: int
    failed_recoveries: int
    ambiguous_operations: int
    success_rate_percentage: float
    attempts_timeline: List[Dict[str, Any]] = []


class FailureCategoryDistribution(BaseModel):
    category: str
    count: int
    percentage: float
    total_amount: float


class FailureMetrics(BaseModel):
    total_failures: int
    categories: List[FailureCategoryDistribution]
    most_common_reason: Optional[str] = None
    repeated_failures_count: int


class AIInsightItem(BaseModel):
    title: str
    severity: str  # HIGH, MEDIUM, LOW
    category: str
    message: str
    suggested_action: str
    affected_subscriptions: int


class AIInsightsResponse(BaseModel):
    insights: List[AIInsightItem]
    generated_at: datetime
