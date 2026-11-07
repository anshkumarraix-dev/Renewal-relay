"""OAuth 2.0 Client Credentials manager with in-memory caching and proactive refresh.

Architectural Guarantees:
- In-memory access-token caching using expires_in minus safety margin.
- asyncio.Lock() serialization prevents race conditions during token refresh.
- Tokens with expires_in <= safety_margin are used once and not cached.
- Credentials and tokens are strictly kept out of logs and string representations.
- Reuses the shared application httpx.AsyncClient connection pool.
"""

import time
import asyncio
import logging
from typing import Optional, Tuple
import httpx

from app.core.config import Settings, settings as default_settings
from app.core.paypal.exceptions import (
    PayPalAuthError,
    PayPalRateLimitError,
    PayPalTransientError,
    PayPalClientError,
)

logger = logging.getLogger("renewal_relay.paypal.auth")


class PayPalAuthManager:
    """Manages OAuth 2.0 client credential tokens with in-memory thread/coroutine-safe caching."""

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or default_settings
        self._access_token: Optional[str] = None
        self._expires_at: Optional[float] = None
        self._lock = asyncio.Lock()

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
        """Perform OAuth 2.0 client credentials grant against PayPal sandbox endpoint."""
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

        try:
            response = await client.post(
                token_url,
                headers=headers,
                data=data,
                auth=(client_id, client_secret),
            )
        except httpx.TimeoutException as exc:
            raise PayPalTransientError(
                message=f"Timeout requesting PayPal OAuth token: {str(exc)}",
                status_code=504,
            ) from exc
        except httpx.NetworkError as exc:
            raise PayPalTransientError(
                message=f"Network error requesting PayPal OAuth token: {str(exc)}",
                status_code=503,
            ) from exc

        # Extract optional debug_id from response
        debug_id = response.headers.get("paypal-debug-id")

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

        if response.status_code == 401:
            raise PayPalAuthError(
                message="PayPal OAuth authentication failed: invalid client credentials.",
                status_code=401,
                debug_id=debug_id,
            )
        if response.status_code == 429:
            raise PayPalRateLimitError(
                message="PayPal OAuth rate limit reached.",
                status_code=429,
                debug_id=debug_id,
            )
        if response.status_code in (500, 502, 503, 504):
            raise PayPalTransientError(
                message=f"PayPal OAuth service unavailable (HTTP {response.status_code}).",
                status_code=response.status_code,
                debug_id=debug_id,
            )

        raise PayPalClientError(
            message=f"Unexpected status from PayPal OAuth endpoint: {response.status_code}",
            status_code=response.status_code,
            debug_id=debug_id,
        )
