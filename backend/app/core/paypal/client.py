"""Resilient, sandbox-isolated PayPal REST API client.

Architectural Guarantees:
- Sandbox endpoint pinned to https://api-m.sandbox.paypal.com.
- Operation safety classification enforced internally; caller claims validated against method and path.
- Strictly ZERO automatic retries on any financial or subscription mutation (including on 429, 502, 503, 504, timeouts).
- Ambiguous outcomes on mutations (timeouts, network drops, HTTP 502/503/504) raise PayPalAmbiguousError.
- Bounded Retry-After (supporting numeric seconds and RFC 7231 HTTP-dates) and full jitter for safe reads.
- One-time token refresh and retry on HTTP 401 for safe reads.
- Strict request URL validation preventing scheme-relative URLs, external hosts, embedded credentials, and queries in path.
- Internal Authorization header protection preventing caller overrides.
- Reuses shared httpx.AsyncClient connection pool without prematurely closing injected clients.
"""

import asyncio
from enum import Enum
import logging
import random
from typing import Optional, Dict, Any, Callable, Awaitable
import httpx

from app.core.config import Settings, settings as default_settings
from app.core.paypal.auth import PayPalAuthManager
from app.core.paypal.exceptions import (
    PayPalClientError,
    PayPalAuthError,
    PayPalRateLimitError,
    PayPalTransientError,
    PayPalBusinessError,
    PayPalAmbiguousError,
)
from app.core.paypal.utils import parse_retry_after, extract_debug_id, validate_api_path

logger = logging.getLogger("renewal_relay.paypal.client")


class OperationSafety(str, Enum):
    """Classification of PayPal API operations by fault-tolerance and retry safety."""
    SAFE_READ = "SAFE_READ"                          # Read-only GET requests (safe to retry on transient errors)
    TOKEN_ACQUISITION = "TOKEN_ACQUISITION"          # POST /v1/oauth2/token (idempotent grant, bounded retries)
    MUTATING_SUBSCRIPTION = "MUTATING_SUBSCRIPTION"  # POST suspend/activate/cancel/revise (state mutation)
    MUTATING_FINANCIAL = "MUTATING_FINANCIAL"        # POST capture (financial charge - strictly NO blind retries)


def classify_operation_safety(
    method: str,
    path: str,
    declared_safety: Optional[OperationSafety] = None,
) -> OperationSafety:
    """Validate and enforce operation safety classification.

    Safeguard: Never trust caller-declared safety without validating HTTP method and path.
    A caller claiming SAFE_READ for a POST /capture or any non-read method will be overridden.
    Unknown non-read operations default to non-retryable mutations.
    """
    method_upper = method.upper()
    clean_path = path.split("?")[0].rstrip("/")

    # 1. Capture endpoint is always MUTATING_FINANCIAL regardless of caller claims
    if "/billing/subscriptions/" in clean_path and clean_path.endswith("/capture"):
        return OperationSafety.MUTATING_FINANCIAL

    # 2. Known subscription mutation endpoints: suspend, activate, cancel, revise
    if "/billing/subscriptions/" in clean_path and any(
        clean_path.endswith(f"/{action}") for action in ("suspend", "activate", "cancel", "revise")
    ):
        return OperationSafety.MUTATING_SUBSCRIPTION

    # 3. Read-only methods (GET, HEAD, OPTIONS) are SAFE_READ
    if method_upper in ("GET", "HEAD", "OPTIONS"):
        return OperationSafety.SAFE_READ

    # 4. OAuth token endpoint is TOKEN_ACQUISITION
    if clean_path.endswith("/v1/oauth2/token"):
        return OperationSafety.TOKEN_ACQUISITION

    # 5. Non-read methods (POST, PUT, PATCH, DELETE) to unknown paths:
    # Caller cannot downgrade a mutation to SAFE_READ.
    if declared_safety == OperationSafety.MUTATING_FINANCIAL:
        return OperationSafety.MUTATING_FINANCIAL

    return OperationSafety.MUTATING_SUBSCRIPTION


class PayPalRESTClient:
    """Secure, resilient PayPal REST client enforcing sandbox isolation and strict mutation safety."""

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        auth_manager: Optional[PayPalAuthManager] = None,
        settings: Optional[Settings] = None,
        sleeper: Optional[Callable[[float], Awaitable[None]]] = None,
        jitter_func: Optional[Callable[[float, float], float]] = None,
    ):
        self._settings = settings or default_settings
        self._owns_client = client is None

        if client is not None:
            self._client = client
        else:
            self._client = httpx.AsyncClient(
                base_url=self._settings.PAYPAL_BASE_URL,
                timeout=httpx.Timeout(self._settings.PAYPAL_TIMEOUT_SECONDS),
                http2=False,
            )

        self._auth = auth_manager or PayPalAuthManager(settings=self._settings)
        self._sleeper = sleeper or asyncio.sleep
        self._jitter_func = jitter_func or random.uniform

    @property
    def http_client(self) -> httpx.AsyncClient:
        """The underlying httpx.AsyncClient shared with the application pool."""
        return self._client

    @property
    def auth_manager(self) -> PayPalAuthManager:
        """The attached OAuth authentication manager."""
        return self._auth

    async def aclose(self) -> None:
        """Close the underlying client ONLY if owned by this instance.

        Externally injected clients (e.g. from FastAPI lifespan or test harnesses) remain open.
        """
        if self._owns_client:
            await self._client.aclose()
            logger.info("Closed internally managed PayPal HTTP client.")

    async def execute(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        declared_safety: Optional[OperationSafety] = None,
    ) -> httpx.Response:
        """Execute a PayPal REST request with strict operation safety and bounded retry controls."""
        # 1. Validate request URL path strictly (reject absolute, scheme-relative, queries, fragments)
        validated_path = validate_api_path(path)

        # 2. Enforce operation safety classification internally
        safety = classify_operation_safety(method=method, path=validated_path, declared_safety=declared_safety)
        is_mutating = safety in (OperationSafety.MUTATING_FINANCIAL, OperationSafety.MUTATING_SUBSCRIPTION)

        # 3. Mutating operations are permitted exactly 1 attempt (ZERO retries)
        max_retries = 0 if is_mutating else self._settings.PAYPAL_MAX_RETRIES

        attempt = 0
        refreshed_on_401 = False

        while True:
            attempt += 1
            retry_count = attempt - 1  # 0 on initial attempt

            # Acquire valid OAuth access token using the shared HTTP connection pool
            access_token = await self._auth.get_access_token(self._client)

            # Build request headers
            req_headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            if headers:
                # Prevent caller-provided headers from overriding or duplicating Authorization
                for k, v in headers.items():
                    if k.lower() != "authorization":
                        req_headers[k] = v

            # Construct Authorization header internally from validated token
            req_headers["Authorization"] = f"Bearer {access_token}"

            # Attach idempotency header if supplied (e.g. for capture)
            if request_id:
                req_headers["PayPal-Request-Id"] = request_id

            # Dispatch request
            try:
                response = await self._client.request(
                    method=method,
                    url=validated_path,
                    headers=req_headers,
                    json=data if data is not None else None,
                    params=params,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as transport_err:
                # SAFEGUARD: On mutating operations, an ambiguous network outcome MUST NOT be retried
                if is_mutating:
                    logger.error(
                        "Ambiguous transport failure during %s %s (request_id=%s): %s. ZERO automatic retries permitted.",
                        method,
                        validated_path,
                        request_id,
                        str(transport_err),
                    )
                    raise PayPalAmbiguousError(
                        message=f"Ambiguous transport failure during {safety.value}: {str(transport_err)}",
                        operation_safety=safety,
                        request_id=request_id,
                        debug_id=None,
                    ) from transport_err

                # For SAFE_READ, retry up to max_retries with jitter
                if retry_count < max_retries:
                    delay = self._jitter_func(0, self._settings.PAYPAL_BACKOFF_FACTOR * (2 ** retry_count))
                    logger.warning(
                        "Transient network error on %s %s (attempt %d/%d): %s. Backing off for %.2fs.",
                        method,
                        validated_path,
                        attempt,
                        max_retries + 1,
                        str(transport_err),
                        delay,
                    )
                    await self._sleeper(delay)
                    continue

                raise PayPalTransientError(
                    message=f"Transient transport failure on {method} {validated_path} after {attempt} attempts: {str(transport_err)}",
                    status_code=504 if isinstance(transport_err, httpx.TimeoutException) else 503,
                    debug_id=None,
                ) from transport_err

            # Extract optional debug ID
            debug_id = extract_debug_id(response)

            # --- Success Responses ---
            if response.status_code in (200, 201, 202, 204):
                return response

            # --- HTTP 401 Unauthorized Handling ---
            if response.status_code == 401:
                # SAFEGUARD: Allow at most ONE token refresh & retry on SAFE_READ only
                if safety == OperationSafety.SAFE_READ and not refreshed_on_401:
                    refreshed_on_401 = True
                    logger.warning("Received 401 on SAFE_READ %s. Invalidating token and retrying once.", validated_path)
                    self._auth.invalidate()
                    continue

                raise PayPalAuthError(
                    message=f"PayPal API authentication failed (HTTP 401) on {method} {validated_path}.",
                    status_code=401,
                    debug_id=debug_id,
                )

            # --- HTTP 429 Rate Limiting Handling ---
            if response.status_code == 429:
                retry_after_delay = parse_retry_after(response.headers.get("retry-after"))

                # SAFEGUARD: Mutating operations NEVER retry automatically, even on 429
                if is_mutating:
                    logger.error(
                        "Received HTTP 429 on mutating operation %s %s (request_id=%s). ZERO automatic retries permitted.",
                        method,
                        validated_path,
                        request_id,
                    )
                    raise PayPalRateLimitError(
                        message=f"PayPal rate limit reached on {safety.value}.",
                        status_code=429,
                        debug_id=debug_id,
                        retry_after=retry_after_delay,
                    )

                # For SAFE_READ, evaluate Retry-After and bounded ceiling
                if retry_count < max_retries:
                    if retry_after_delay is not None:
                        if retry_after_delay > self._settings.PAYPAL_MAX_RETRY_AFTER_SECONDS:
                            raise PayPalRateLimitError(
                                message=(
                                    f"Rate limited: Retry-After ({retry_after_delay:.1f}s) exceeds "
                                    f"configured ceiling ({self._settings.PAYPAL_MAX_RETRY_AFTER_SECONDS:.1f}s)."
                                ),
                                status_code=429,
                                debug_id=debug_id,
                                retry_after=retry_after_delay,
                            )
                        delay = retry_after_delay
                    else:
                        delay = self._jitter_func(0, self._settings.PAYPAL_BACKOFF_FACTOR * (2 ** retry_count))

                    logger.warning(
                        "Rate limited on %s %s (attempt %d/%d). Sleeping for %.2fs.",
                        method,
                        validated_path,
                        attempt,
                        max_retries + 1,
                        delay,
                    )
                    await self._sleeper(delay)
                    continue

                raise PayPalRateLimitError(
                    message=f"PayPal rate limit reached on {method} {validated_path} after {attempt} attempts.",
                    status_code=429,
                    debug_id=debug_id,
                    retry_after=retry_after_delay,
                )

            # --- HTTP 502, 503, 504 Transient Server Errors ---
            if response.status_code in (502, 503, 504):
                if is_mutating:
                    logger.error(
                        "Ambiguous HTTP %d response on mutating operation %s %s (request_id=%s). ZERO automatic retries permitted.",
                        response.status_code,
                        method,
                        validated_path,
                        request_id,
                    )
                    raise PayPalAmbiguousError(
                        message=f"Ambiguous server response (HTTP {response.status_code}) during {safety.value}.",
                        operation_safety=safety,
                        request_id=request_id,
                        debug_id=debug_id,
                        status_code=response.status_code,
                    )

                if retry_count < max_retries:
                    delay = self._jitter_func(0, self._settings.PAYPAL_BACKOFF_FACTOR * (2 ** retry_count))
                    logger.warning(
                        "Transient HTTP %d error on %s %s (attempt %d/%d). Sleeping for %.2fs.",
                        response.status_code,
                        method,
                        validated_path,
                        attempt,
                        max_retries + 1,
                        delay,
                    )
                    await self._sleeper(delay)
                    continue

                raise PayPalTransientError(
                    message=f"PayPal server error (HTTP {response.status_code}) on {method} {validated_path}.",
                    status_code=response.status_code,
                    debug_id=debug_id,
                )

            # --- HTTP 422 Unprocessable Entity ---
            if response.status_code == 422:
                err_name = None
                details = None
                try:
                    err_json = response.json()
                    err_name = err_json.get("name")
                    details = err_json.get("details")
                except Exception:
                    pass

                raise PayPalBusinessError(
                    message=f"PayPal business validation failed (HTTP 422) on {method} {validated_path}.",
                    status_code=422,
                    debug_id=debug_id,
                    error_name=err_name,
                    details=details,
                )

            # --- Default Client Error ---
            raise PayPalClientError(
                message=f"PayPal API request failed (HTTP {response.status_code}) on {method} {validated_path}.",
                status_code=response.status_code,
                debug_id=debug_id,
            )
