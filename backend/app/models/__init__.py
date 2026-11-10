"""Central export point for all SQLAlchemy domain models.

Allows Base.metadata to automatically discover and create all tables.
"""

from app.models.subscription import (
    Merchant,
    BillingPlan,
    Subscription,
    PaymentTransaction,
    PaymentFailure,
    SubscriptionStateHistory,
)
from app.models.webhook import WebhookEvent
from app.models.recovery import (
    RecoveryOpportunity,
    RecoveryEvaluation,
    MerchantApproval,
    RecoveryOperation,
    AIRecommendation,
    AuditLog,
)

__all__ = [
    "Merchant",
    "BillingPlan",
    "Subscription",
    "PaymentTransaction",
    "PaymentFailure",
    "SubscriptionStateHistory",
    "WebhookEvent",
    "RecoveryOpportunity",
    "RecoveryEvaluation",
    "MerchantApproval",
    "RecoveryOperation",
    "AIRecommendation",
    "AuditLog",
]
