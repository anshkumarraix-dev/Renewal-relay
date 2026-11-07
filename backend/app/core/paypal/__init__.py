"""PayPal Core Integration Package for Renewal Relay.

Exports:
- PayPalRESTClient: Primary asynchronous REST API client.
- PayPalAuthManager: OAuth 2.0 Client Credentials token lifecycle manager.
- OperationSafety: Operation risk classification enum.
- Exceptions: Structured PayPal error hierarchy.
"""

from app.core.paypal.exceptions import (
    PayPalClientError,
    PayPalAuthError,
    PayPalRateLimitError,
    PayPalTransientError,
    PayPalBusinessError,
    PayPalAmbiguousError,
)
from app.core.paypal.auth import PayPalAuthManager
from app.core.paypal.client import PayPalRESTClient, OperationSafety, classify_operation_safety

__all__ = [
    "PayPalRESTClient",
    "PayPalAuthManager",
    "OperationSafety",
    "classify_operation_safety",
    "PayPalClientError",
    "PayPalAuthError",
    "PayPalRateLimitError",
    "PayPalTransientError",
    "PayPalBusinessError",
    "PayPalAmbiguousError",
]
