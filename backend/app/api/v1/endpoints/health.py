"""Health check endpoints for system, database, and governance verification.

Requirement: Perform real SQLite connectivity check using SQLAlchemy.
Requirement: Return separate application and database statuses.
Requirement: Do not perform external PayPal API requests on health check.
"""

from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, status, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, check_database_health
from app.schemas.health import HealthResponse, ComponentStatus

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Comprehensive system health check",
    description="Validates FastAPI runtime and verifies actual SQLite database connectivity with separate statuses.",
)
def get_health(
    response: Response,
    db: Session = Depends(get_db),
) -> HealthResponse:
    """Return health status of application and database separately."""
    # 1. Application status
    app_status = ComponentStatus(
        status="operational",
        latency_ms=0.0,
        message="FastAPI service is running",
    )

    # 2. Database status (Real SQLite query via SQLAlchemy)
    is_db_connected, db_latency_ms, db_error = check_database_health(db)
    if is_db_connected:
        db_status = ComponentStatus(
            status="operational",
            latency_ms=db_latency_ms,
            message="SQLite database connection verified",
        )
        overall_status = "healthy"
    else:
        db_status = ComponentStatus(
            status="error",
            latency_ms=db_latency_ms,
            message=db_error or "Database connectivity failed",
        )
        overall_status = "degraded"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # 3. PayPal status metadata (No external API calls per architecture rules)
    paypal_metadata = {
        "mode": settings.PAYPAL_MODE,
        "status": "configured_offline",
        "external_polling": False,
        "notice": "External PayPal API requests are excluded from health checks",
    }

    # 4. Governance metadata
    governance_metadata = {
        "deterministic_policy_enforced": settings.ENFORCE_DETERMINISTIC_POLICY,
        "ai_autonomous_payment_allowed": settings.ALLOW_AI_AUTONOMOUS_PAYMENT,
        "payment_authority": "PayPal",
    }

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
        app=app_status,
        database=db_status,
        paypal=paypal_metadata,
        governance=governance_metadata,
    )


@router.get(
    "/health/live",
    summary="Basic liveness probe",
    description="Lightweight check confirming FastAPI process is responsive.",
)
def get_liveness() -> dict:
    """Return fast liveness confirmation without executing database queries."""
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
