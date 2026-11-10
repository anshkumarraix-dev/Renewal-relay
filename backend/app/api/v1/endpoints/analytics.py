"""Revenue Analytics and Executive Dashboard Endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.analytics_service import AnalyticsService
from app.schemas.analytics import (
    OverviewMetrics,
    RevenueMetrics,
    RecoveryMetrics,
    FailureMetrics,
    AIInsightsResponse,
)

router = APIRouter()


@router.get("/overview", response_model=OverviewMetrics, summary="Executive overview KPIs")
def get_overview(db: Session = Depends(get_db)):
    """Retrieve top-level KPI metrics for the executive dashboard."""
    service = AnalyticsService(db)
    return service.get_overview_metrics()


@router.get("/revenue", response_model=RevenueMetrics, summary="Revenue recovery metrics")
def get_revenue_metrics(db: Session = Depends(get_db)):
    """Retrieve verified recovered revenue, outstanding balance, and monthly trends."""
    service = AnalyticsService(db)
    return service.get_revenue_metrics()


@router.get("/recovery", response_model=RecoveryMetrics, summary="Recovery operations metrics")
def get_recovery_metrics(db: Session = Depends(get_db)):
    """Retrieve recovery attempt success rates, counts, and timeline."""
    service = AnalyticsService(db)
    return service.get_recovery_metrics()


@router.get("/failures", response_model=FailureMetrics, summary="Payment failure distribution")
def get_failure_metrics(db: Session = Depends(get_db)):
    """Retrieve failure category breakdown and repeated decline statistics."""
    service = AnalyticsService(db)
    return service.get_failure_metrics()


@router.get("/ai-insights", response_model=AIInsightsResponse, summary="AI merchant intelligence alerts")
def get_ai_insights(db: Session = Depends(get_db)):
    """Retrieve prioritized merchant advisory alerts, churn risks, and suggested actions."""
    service = AnalyticsService(db)
    return service.get_ai_insights()
