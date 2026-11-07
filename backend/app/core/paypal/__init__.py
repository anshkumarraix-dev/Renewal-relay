"""PayPal Core Integration Package for Renewal Relay.

Exports:
- PayPalRESTClient: Primary asynchronous REST API client.
- PayPalAuthManager: OAuth 2.0 Client Credentials token lifecycle manager.
- OperationSafety: Operation risk classification enum.
- Exceptions: Structured PayPal error hierarchy.
- Utilities: validate_api_path, parse_retry_after, extract_debug_id.
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
from app.core.paypal.utils import parse_retry_after, extract_debug_id, validate_api_path

__all__ = [
    "PayPalRESTClient",
    "PayPalAuthManager",
    "OperationSafety",
    "classify_operation_safety",
    "parse_retry_after",
    "extract_debug_id",
    "validate_api_path",
    "PayPalClientError",
    "PayPalAuthError",
    "PayPalRateLimitError",
    "PayPalTransientError",
    "PayPalBusinessError",
    "PayPalAmbiguousError",
]
