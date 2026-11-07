"""Structured exception hierarchy for PayPal REST API interactions.

Rule: debug_id is optional and only extracted from upstream headers or body.
Never fabricate debug IDs for network timeouts or client-side errors.
"""

from typing import Optional, List, Any


class PayPalClientError(Exception):
    """Base exception for all PayPal REST client operations."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        debug_id: Optional[str] = None,
        error_name: Optional[str] = None,
        details: Optional[List[Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.debug_id = debug_id
        self.error_name = error_name
        self.details = details or []

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.debug_id:
            parts.append(f"debug_id={self.debug_id}")
        if self.error_name:
            parts.append(f"name={self.error_name}")
        return " | ".join(parts)


class PayPalAuthError(PayPalClientError):
    """Raised when authentication fails (HTTP 401 Unauthorized)."""
    pass


class PayPalRateLimitError(PayPalClientError):
    """Raised when rate limits are exceeded (HTTP 429 Too Many Requests)."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = 429,
        debug_id: Optional[str] = None,
        retry_after: Optional[float] = None,
        error_name: Optional[str] = "RATE_LIMIT_REACHED",
        details: Optional[List[Any]] = None,
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            debug_id=debug_id,
            error_name=error_name,
            details=details,
        )
        self.retry_after = retry_after


class PayPalTransientError(PayPalClientError):
    """Raised on transient server errors (HTTP 502, 503, 504)."""
    pass


class PayPalBusinessError(PayPalClientError):
    """Raised on business logic / unprocessable entity rejections (HTTP 422)."""
    pass


class PayPalAmbiguousError(PayPalClientError):
    """Raised when a mutating operation encounters an uncertain outcome (e.g. timeout or drop).

    Indicates that the operation may or may not have been processed by PayPal.
    Never automatically retried; must be returned to the service layer for reconciliation.
    """

    def __init__(
        self,
        message: str,
        operation_safety: Any,
        request_id: Optional[str] = None,
        debug_id: Optional[str] = None,
        error_name: Optional[str] = "AMBIGUOUS_MUTATION_OUTCOME",
    ):
        super().__init__(
            message=message,
            status_code=None,
            debug_id=debug_id,
            error_name=error_name,
        )
        self.operation_safety = operation_safety
        self.request_id = request_id

    def __str__(self) -> str:
        safety_str = getattr(self.operation_safety, "value", str(self.operation_safety))
        parts = [self.message, f"operation_safety={safety_str}"]
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        if self.debug_id:
            parts.append(f"debug_id={self.debug_id}")
        return " | ".join(parts)
