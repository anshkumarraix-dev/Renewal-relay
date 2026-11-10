"""API v1 router composition."""

from fastapi import APIRouter
from app.api.v1.endpoints import (
    health,
    subscriptions,
    webhooks,
    recovery,
    analytics,
    demo,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(recovery.router, prefix="/recovery", tags=["Recovery"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(demo.router, prefix="/demo", tags=["Demo Simulation"])
