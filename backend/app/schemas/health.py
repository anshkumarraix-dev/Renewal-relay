"""Health check schemas with separated application and database status models."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    """Status details for an individual system component."""
    status: str = Field(description="Component operational status: operational, degraded, or error")
    latency_ms: Optional[float] = Field(default=None, description="Response latency in milliseconds")
    message: Optional[str] = Field(default=None, description="Diagnostic details or error message")


class HealthResponse(BaseModel):
    """Comprehensive health check response returning separate app and DB statuses."""
    status: str = Field(description="Overall system status: healthy or degraded")
    timestamp: str = Field(description="ISO-8601 UTC timestamp of the health check")
    environment: str = Field(description="Active runtime environment name")
    version: str = Field(description="Application version")
    app: ComponentStatus = Field(description="FastAPI application status")
    database: ComponentStatus = Field(description="SQLite database connectivity status")
    paypal: Dict[str, Any] = Field(
        description="PayPal mode status without external network polling"
    )
    governance: Dict[str, Any] = Field(
        description="Policy enforcement boundaries and authorization guards"
    )
