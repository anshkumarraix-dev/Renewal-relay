"""OAuth 2.0 Client Credentials manager with in-memory caching and proactive refresh.

Architectural Guarantees:
- In-memory access-token caching using expires_in minus safety margin.
- asyncio.Lock() serialization prevents race conditions during token refresh.
- Tokens with expires_in <= safety_margin are used once and not cached.
- Credentials and tokens are strictly kept out of logs and string representations.
- Bounded retries for transient token acquisition failures (timeouts, network drops, HTTP 502/503/504, 429).
- Bounded Retry-After ceiling enforcement.
- Injectable sleeper and jitter functions for deterministic unit testing.
- Reuses the shared application httpx.AsyncClient connection pool.
"""

import time
import asyncio
import logging
import random
from typing import Optional, Tuple, Callable, Awaitable
import httpx

from app.core.config import Settings, settings as default_settings
from app.core.paypal.exceptions import (
    PayPalAuthError,
    PayPalRateLimitError,
    PayPalTransientError,
    PayPalClientError,
)
from app.core.paypal.utils import parse_retry_after, extract_debug_id

logger = logging.getLogger("renewal_relay.paypal.auth")


class PayPalAuthManager:
    """Manages OAuth 2.0 client credential tokens with in-memory thread/coroutine-safe caching."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sleeper: Optional[Callable[[float], Awaitable[None]]] = None,
        jitter_func: Optional[Callable[[float, float], float]] = None,
    ):
        self._settings = settings or default_settings
        self._access_token: Optional[str] = None
        self._expires_at: Optional[float] = None
        self._lock = asyncio.Lock()
        self._sleeper = sleeper or asyncio.sleep
        self._jitter_func = jitter_func or random.uniform

    def __repr__(self) -> str:
        cached = "yes" if self.has_valid_token() else "no"
        return f"<PayPalAuthManager cached_token={cached}>"

    def has_valid_token(self) -> bool:
        """Check if a valid unexpired access token is currently cached in memory."""
        if self._access_token is None or self._expires_at is None:
            return False
        return time.monotonic() < self._expires_at

    def invalidate(self) -> None:
        """Explicitly clear the cached access token in memory."""
        self._access_token = None
        self._expires_at = None
        logger.info("PayPal in-memory access token invalidated.")

    async def get_access_token(self, client: httpx.AsyncClient) -> str:
        """Acquire an active OAuth 2.0 access token, returning the cached token or fetching a fresh one.

        Concurrency is protected by asyncio.Lock() so only a single flight requests a token from PayPal.
        """
        now = time.monotonic()
        if self._access_token is not None and self._expires_at is not None and now < self._expires_at:
            return self._access_token

        async with self._lock:
            now = time.monotonic()
            if self._access_token is not None and self._expires_at is not None and now < self._expires_at:
                return self._access_token

            token, expires_in = await self._fetch_token(client)

            safety_margin = self._settings.PAYPAL_TOKEN_SAFETY_MARGIN_SECONDS
            if expires_in <= safety_margin:
                logger.warning(
                    "Token expires_in (%ds) <= safety_margin (%ds); using token once without caching.",
                    expires_in,
                    safety_margin,
                )
                self._access_token = None
                self._expires_at = None
                return token

            self._access_token = token
            self._expires_at = time.monotonic() + expires_in - safety_margin
            logger.info("Successfully refreshed and cached PayPal access token (valid for ~%ds).", expires_in)
            return self._access_token

    async def _fetch_token(self, client: httpx.AsyncClient) -> Tuple[str, int]:
        """Perform OAuth 2.0 client credentials grant against PayPal sandbox endpoint with bounded retries."""
        token_url = f"{self._settings.PAYPAL_BASE_URL}/v1/oauth2/token"
        client_id = self._settings.PAYPAL_CLIENT_ID
        client_secret = self._settings.PAYPAL_CLIENT_SECRET

        if not client_id or not client_secret:
            raise PayPalAuthError(
                message="Cannot request PayPal access token: PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET is missing.",
                status_code=401,
            )

        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {"grant_type": "client_credentials"}

        max_retries = self._settings.PAYPAL_MAX_RETRIES
        attempt = 0

        while True:
            attempt += 1
            retry_count = attempt - 1

            try:
                response = await client.post(
                    token_url,
                    headers=headers,
                    data=data,
                    auth=(client_id, client_secret),
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if retry_count < max_retries:
                    delay = self._jitter_func(0, self._settings.PAYPAL_BACKOFF_FACTOR * (2 ** retry_count))
                    logger.warning(
                        "Transient network failure requesting PayPal OAuth token (attempt %d/%d). Backing off for %.2fs.",
                        attempt,
                        max_retries + 1,
                        delay,
                    )
                    await self._sleeper(delay)
                    continue

                status_code = 504 if isinstance(exc, httpx.TimeoutException) else 503
                raise PayPalTransientError(
                    message=f"Transient transport failure requesting PayPal OAuth token after {attempt} attempts: {str(exc)}",
                    status_code=status_code,
                    debug_id=None,
                ) from exc

            # Extract optional debug_id from response (never fabricated)
            debug_id = extract_debug_id(response)

            if response.status_code == 200:
                try:
                    payload = response.json()
                except Exception as exc:
                    raise PayPalClientError(
                        message="Malformed JSON response from PayPal OAuth endpoint",
                        status_code=200,
                        debug_id=debug_id,
                    ) from exc

                access_token = payload.get("access_token")
                expires_in = payload.get("expires_in")

                if not access_token or not isinstance(expires_in, (int, float)):
                    raise PayPalClientError(
                        message="Invalid token response payload: missing access_token or expires_in",
                        status_code=200,
                        debug_id=debug_id,
                    )

                return access_token, int(expires_in)

            # HTTP 401 Unauthorized: Invalid credentials - do NOT retry
            if response.status_code == 401:
                raise PayPalAuthError(
                    message="PayPal OAuth authentication failed: invalid client credentials.",
                    status_code=401,
                    debug_id=debug_id,
                )

            # HTTP 429 Rate Limit: evaluate bounded Retry-After
            if response.status_code == 429:
                retry_after_delay = parse_retry_after(response.headers.get("retry-after"))
                if retry_count < max_retries:
                    if retry_after_delay is not None:
                        if retry_after_delay > self._settings.PAYPAL_MAX_RETRY_AFTER_SECONDS:
                            raise PayPalRateLimitError(
                                message=(
                                    f"PayPal OAuth rate limited: Retry-After ({retry_after_delay:.1f}s) exceeds "
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
                        "PayPal OAuth rate limited (attempt %d/%d). Sleeping for %.2fs.",
                        attempt,
                        max_retries + 1,
                        delay,
                    )
                    await self._sleeper(delay)
                    continue

                raise PayPalRateLimitError(
                    message=f"PayPal OAuth rate limit reached after {attempt} attempts.",
                    status_code=429,
                    debug_id=debug_id,
                    retry_after=retry_after_delay,
                )

            # HTTP 500, 502, 503, 504: Transient server errors
            if response.status_code in (500, 502, 503, 504):
                if retry_count < max_retries:
                    delay = self._jitter_func(0, self._settings.PAYPAL_BACKOFF_FACTOR * (2 ** retry_count))
                    logger.warning(
                        "Transient HTTP %d on PayPal OAuth token request (attempt %d/%d). Sleeping for %.2fs.",
                        response.status_code,
                        attempt,
                        max_retries + 1,
                        delay,
                    )
                    await self._sleeper(delay)
                    continue

                raise PayPalTransientError(
                    message=f"PayPal OAuth service unavailable (HTTP {response.status_code}) after {attempt} attempts.",
                    status_code=response.status_code,
                    debug_id=debug_id,
                )

            # Non-retryable error
            raise PayPalClientError(
                message=f"Unexpected status from PayPal OAuth endpoint: {response.status_code}",
                status_code=response.status_code,
                debug_id=debug_id,
            )
