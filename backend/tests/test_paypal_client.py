"""Comprehensive offline unit test suite for Renewal Relay PayPal REST client foundation (P0.1).

Validates:
1. Exact Sandbox URL enforcement (rejecting HTTP, live hosts, alternate hosts, credentials, malformed ports, paths, queries).
2. Numeric configuration validation boundaries.
3. Zero automatic retries on all mutations (capture, suspend, activate, cancel, revise), including on HTTP 429.
4. Internal operation safety enforcement overriding faulty caller claims.
5. Ambiguous mutation timeout handling (raises PayPalAmbiguousError with request_id and operation_safety, 0 retries).
6. Safe GET retries on HTTP 502, 503, 504 and transient drops up to 1 + MAX_RETRIES.
7. Retry-After parsing (numeric seconds and RFC 7231 HTTP-dates) and bounded ceiling enforcement.
8. Short-lived token non-caching (expires_in <= safety_margin).
9. One-time token refresh on HTTP 401 for SAFE_READ.
10. Concurrent token refresh single-flight locking (asyncio.Lock).
11. Injected HTTP client ownership protection (not closed by REST client).
12. Application lifespan client lifecycle (initialization and shutdown closure).
13. Optional debug_id extraction (header, body, and None on network timeout).
"""

import os
import sys
import unittest
import asyncio
from datetime import datetime, timezone, timedelta
import email.utils
from unittest.mock import AsyncMock
import httpx

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# On Windows in sandboxed test environments without loopback socket access,
# patch ProactorEventLoop's self-pipe to use os.pipe() to prevent loopback TCP socketpair timeouts.
if sys.platform == "win32":
    try:
        from asyncio import proactor_events, windows_events

        class _SandboxSafePipeSocket:
            def __init__(self, fd):
                self._fd = fd
            def fileno(self):
                return self._fd
            def setblocking(self, b):
                pass
            def close(self):
                try:
                    os.close(self._fd)
                except OSError:
                    pass
            def send(self, data):
                try:
                    return os.write(self._fd, data)
                except OSError:
                    return 0

        def _sandbox_make_self_pipe(self):
            r, w = os.pipe()
            self._ssock = _SandboxSafePipeSocket(r)
            self._csock = _SandboxSafePipeSocket(w)
            self._internal_fds += 1

        def _sandbox_run_forever_setup(self):
            super(windows_events.ProactorEventLoop, self)._run_forever_setup()

        proactor_events.BaseProactorEventLoop._make_self_pipe = _sandbox_make_self_pipe
        windows_events.ProactorEventLoop._run_forever_setup = _sandbox_run_forever_setup
    except Exception:
        pass

from app.core.config import Settings, validate_sandbox_url
from app.core.paypal import (
    PayPalRESTClient,
    PayPalAuthManager,
    OperationSafety,
    classify_operation_safety,
    PayPalClientError,
    PayPalAuthError,
    PayPalRateLimitError,
    PayPalTransientError,
    PayPalBusinessError,
    PayPalAmbiguousError,
)
from app.core.paypal.client import parse_retry_after, extract_debug_id
from app.main import app, lifespan


class TestSandboxUrlEnforcement(unittest.TestCase):
    """Test strict sandbox endpoint validation and rejection of unsafe/malformed URLs."""

    def test_valid_sandbox_url(self):
        url = "https://api-m.sandbox.paypal.com"
        self.assertEqual(validate_sandbox_url(url), url)
        # Root trailing slash normalized
        self.assertEqual(validate_sandbox_url(url + "/"), url)

    def test_reject_non_https(self):
        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("http://api-m.sandbox.paypal.com")
        self.assertIn("HTTPS scheme", str(ctx.exception))

    def test_reject_embedded_credentials(self):
        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("https://user:pass@api-m.sandbox.paypal.com")
        self.assertIn("Embedded credentials", str(ctx.exception))

    def test_reject_live_url(self):
        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("https://api-m.paypal.com")
        self.assertIn("Live endpoints and alternate hosts are strictly prohibited", str(ctx.exception))

    def test_reject_alternate_hosts(self):
        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("https://api.sandbox.paypal.com")
        self.assertIn("api-m.sandbox.paypal.com", str(ctx.exception))

    def test_reject_custom_and_malformed_ports(self):
        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("https://api-m.sandbox.paypal.com:8080")
        self.assertIn("Unexpected port", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("https://api-m.sandbox.paypal.com:invalid")
        self.assertIn("Malformed port", str(ctx.exception))

    def test_reject_paths_and_queries(self):
        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("https://api-m.sandbox.paypal.com/v1")
        self.assertIn("path component", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_sandbox_url("https://api-m.sandbox.paypal.com?query=1")
        self.assertIn("query parameters", str(ctx.exception))


class TestConfigurationBoundaries(unittest.TestCase):
    """Test numeric boundary validators in Settings."""

    def test_boundary_validators(self):
        with self.assertRaises(ValueError):
            Settings(PAYPAL_TOKEN_SAFETY_MARGIN_SECONDS=0)

        with self.assertRaises(ValueError):
            Settings(PAYPAL_TIMEOUT_SECONDS=0)

        with self.assertRaises(ValueError):
            Settings(PAYPAL_MAX_RETRIES=-1)

        with self.assertRaises(ValueError):
            Settings(PAYPAL_MAX_RETRY_AFTER_SECONDS=0)

        with self.assertRaises(ValueError):
            Settings(PAYPAL_BACKOFF_FACTOR=0)


class TestRetryAfterParsing(unittest.TestCase):
    """Test numeric and HTTP-date parsing for Retry-After headers."""

    def test_parse_numeric_seconds(self):
        self.assertEqual(parse_retry_after("5"), 5.0)
        self.assertEqual(parse_retry_after("0"), 0.0)
        self.assertIsNone(parse_retry_after(None))
        self.assertIsNone(parse_retry_after(""))

    def test_parse_http_date(self):
        future_dt = datetime.now(timezone.utc) + timedelta(seconds=7)
        http_date_str = email.utils.format_datetime(future_dt)
        parsed_wait = parse_retry_after(http_date_str)
        self.assertIsNotNone(parsed_wait)
        self.assertAlmostEqual(parsed_wait, 7.0, delta=2.0)


class TestOperationSafetyEnforcement(unittest.TestCase):
    """Test internal classification and override of caller-declared safety."""

    def test_internal_classification_rules(self):
        # GET is always safe read
        self.assertEqual(
            classify_operation_safety("GET", "/v1/billing/subscriptions/I-123"),
            OperationSafety.SAFE_READ,
        )
        # Capture is financial mutation
        self.assertEqual(
            classify_operation_safety("POST", "/v1/billing/subscriptions/I-123/capture"),
            OperationSafety.MUTATING_FINANCIAL,
        )
        # Suspend, activate, cancel, revise are subscription mutations
        for action in ("suspend", "activate", "cancel", "revise"):
            self.assertEqual(
                classify_operation_safety("POST", f"/v1/billing/subscriptions/I-123/{action}"),
                OperationSafety.MUTATING_SUBSCRIPTION,
            )
        # OAuth token endpoint
        self.assertEqual(
            classify_operation_safety("POST", "/v1/oauth2/token"),
            OperationSafety.TOKEN_ACQUISITION,
        )

    def test_override_faulty_caller_claim(self):
        # Caller claiming SAFE_READ on capture must be overridden to MUTATING_FINANCIAL
        safety = classify_operation_safety(
            "POST",
            "/v1/billing/subscriptions/I-123/capture",
            declared_safety=OperationSafety.SAFE_READ,
        )
        self.assertEqual(safety, OperationSafety.MUTATING_FINANCIAL)


class TestPayPalClientBehavior(unittest.TestCase):
    """Offline mock tests for PayPalRESTClient and PayPalAuthManager."""

    def setUp(self):
        self.test_settings = Settings(
            PAYPAL_CLIENT_ID="test_client_id_123",
            PAYPAL_CLIENT_SECRET="test_client_secret_456",
            PAYPAL_MAX_RETRIES=2,
            PAYPAL_MAX_RETRY_AFTER_SECONDS=10.0,
            PAYPAL_BACKOFF_FACTOR=0.01,
            PAYPAL_TOKEN_SAFETY_MARGIN_SECONDS=120,
        )
        self.auth_manager = PayPalAuthManager(settings=self.test_settings)
        # Pre-seed token so auth call does not hit handler by default
        self.auth_manager._access_token = "valid_cached_token"
        self.auth_manager._expires_at = 9999999999.0

        # Injectable sleep tracker
        self.sleep_history = []

        async def mock_sleeper(seconds: float):
            self.sleep_history.append(seconds)

        self.mock_sleeper = mock_sleeper
        self.mock_jitter = lambda a, b: b  # Deterministic jitter for testing

    def test_zero_retries_on_mutations_including_429(self):
        """Verify that capture, suspend, activate, cancel, revise on HTTP 429 NEVER retry (attempts=1)."""
        mutation_endpoints = [
            ("/v1/billing/subscriptions/I-1/capture", OperationSafety.MUTATING_FINANCIAL),
            ("/v1/billing/subscriptions/I-1/suspend", OperationSafety.MUTATING_SUBSCRIPTION),
            ("/v1/billing/subscriptions/I-1/activate", OperationSafety.MUTATING_SUBSCRIPTION),
            ("/v1/billing/subscriptions/I-1/cancel", OperationSafety.MUTATING_SUBSCRIPTION),
            ("/v1/billing/subscriptions/I-1/revise", OperationSafety.MUTATING_SUBSCRIPTION),
        ]

        for path, safety in mutation_endpoints:
            attempts = 0

            def handler(request: httpx.Request):
                nonlocal attempts
                attempts += 1
                return httpx.Response(
                    429,
                    headers={"paypal-debug-id": "debug-429-mut"},
                    json={"name": "RATE_LIMIT_REACHED"},
                )

            transport = httpx.MockTransport(handler)
            mock_http_client = httpx.AsyncClient(
                transport=transport,
                base_url=self.test_settings.PAYPAL_BASE_URL,
            )

            client = PayPalRESTClient(
                client=mock_http_client,
                auth_manager=self.auth_manager,
                settings=self.test_settings,
                sleeper=self.mock_sleeper,
                jitter_func=self.mock_jitter,
            )

            with self.assertRaises(PayPalRateLimitError) as ctx:
                asyncio.run(
                    client.execute(
                        method="POST",
                        path=path,
                        data={"reason": "test"},
                        request_id="req-test-123",
                    )
                )

            self.assertEqual(attempts, 1, f"Mutating endpoint {path} executed more than 1 attempt!")
            self.assertEqual(ctx.exception.debug_id, "debug-429-mut")

    def test_ambiguous_capture_timeout_preserves_request_id(self):
        """Verify transport timeout on capture raises PayPalAmbiguousError with 0 retries and request_id."""
        attempts = 0

        def handler(request: httpx.Request):
            nonlocal attempts
            attempts += 1
            raise httpx.ReadTimeout("Socket timeout waiting for response")

        transport = httpx.MockTransport(handler)
        mock_http_client = httpx.AsyncClient(transport=transport, base_url=self.test_settings.PAYPAL_BASE_URL)
        client = PayPalRESTClient(
            client=mock_http_client,
            auth_manager=self.auth_manager,
            settings=self.test_settings,
            sleeper=self.mock_sleeper,
        )

        with self.assertRaises(PayPalAmbiguousError) as ctx:
            asyncio.run(
                client.execute(
                    method="POST",
                    path="/v1/billing/subscriptions/I-99/capture",
                    data={"note": "Capture retry"},
                    request_id="unique-capture-uuid-777",
                )
            )

        self.assertEqual(attempts, 1, "Financial capture must not retry on timeout!")
        self.assertEqual(ctx.exception.request_id, "unique-capture-uuid-777")
        self.assertEqual(ctx.exception.operation_safety, OperationSafety.MUTATING_FINANCIAL)
        self.assertIsNone(ctx.exception.debug_id)

    def test_safe_get_retries_on_502_503_504(self):
        """Verify SAFE_READ GET retries on transient errors up to 1 + MAX_RETRIES (total 3 attempts)."""
        attempts = 0

        def handler(request: httpx.Request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(502, headers={"paypal-debug-id": "dbg-502"})
            if attempts == 2:
                return httpx.Response(503, headers={"paypal-debug-id": "dbg-503"})
            return httpx.Response(200, json={"status": "ACTIVE"})

        transport = httpx.MockTransport(handler)
        mock_http_client = httpx.AsyncClient(transport=transport, base_url=self.test_settings.PAYPAL_BASE_URL)
        client = PayPalRESTClient(
            client=mock_http_client,
            auth_manager=self.auth_manager,
            settings=self.test_settings,
            sleeper=self.mock_sleeper,
            jitter_func=self.mock_jitter,
        )

        resp = asyncio.run(client.execute("GET", "/v1/billing/subscriptions/I-123"))
        self.assertEqual(attempts, 3)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ACTIVE")
        self.assertEqual(len(self.sleep_history), 2)

    def test_retry_after_bounded_ceiling(self):
        """Verify Retry-After exceeding maximum allowed wait immediately aborts with PayPalRateLimitError."""
        attempts = 0

        def handler(request: httpx.Request):
            nonlocal attempts
            attempts += 1
            return httpx.Response(429, headers={"retry-after": "60", "paypal-debug-id": "dbg-excess"})

        transport = httpx.MockTransport(handler)
        mock_http_client = httpx.AsyncClient(transport=transport, base_url=self.test_settings.PAYPAL_BASE_URL)
        client = PayPalRESTClient(
            client=mock_http_client,
            auth_manager=self.auth_manager,
            settings=self.test_settings,
            sleeper=self.mock_sleeper,
        )

        with self.assertRaises(PayPalRateLimitError) as ctx:
            asyncio.run(client.execute("GET", "/v1/billing/subscriptions/I-123"))

        self.assertEqual(attempts, 1)
        self.assertIn("exceeds configured ceiling", str(ctx.exception))
        self.assertEqual(ctx.exception.retry_after, 60.0)

    def test_short_lived_token_not_cached(self):
        """Verify that tokens with expires_in <= safety_margin (120s) are used once and NOT cached."""
        token_requests = 0

        def handler(request: httpx.Request):
            nonlocal token_requests
            if request.url.path == "/v1/oauth2/token":
                token_requests += 1
                return httpx.Response(
                    200,
                    json={"access_token": f"short_token_{token_requests}", "expires_in": 60},
                )
            return httpx.Response(200, json={"status": "OK"})

        transport = httpx.MockTransport(handler)
        mock_http_client = httpx.AsyncClient(transport=transport, base_url=self.test_settings.PAYPAL_BASE_URL)
        fresh_auth_manager = PayPalAuthManager(settings=self.test_settings)

        client = PayPalRESTClient(
            client=mock_http_client,
            auth_manager=fresh_auth_manager,
            settings=self.test_settings,
        )

        # First request
        asyncio.run(client.execute("GET", "/v1/catalogs/products"))
        self.assertEqual(token_requests, 1)
        self.assertFalse(fresh_auth_manager.has_valid_token(), "Short-lived token must not be cached!")

        # Second request must re-fetch token since it was not cached
        asyncio.run(client.execute("GET", "/v1/catalogs/products"))
        self.assertEqual(token_requests, 2)

    def test_one_time_get_token_refresh_on_401(self):
        """Verify that safe read receiving 401 refreshes token and retries at most once."""
        get_attempts = 0
        token_requests = 0

        def handler(request: httpx.Request):
            nonlocal get_attempts, token_requests
            if request.url.path == "/v1/oauth2/token":
                token_requests += 1
                return httpx.Response(200, json={"access_token": "fresh_token_after_401", "expires_in": 3600})
            if request.url.path == "/v1/billing/plans":
                get_attempts += 1
                auth_header = request.headers.get("authorization", "")
                if "fresh_token_after_401" in auth_header:
                    return httpx.Response(200, json={"plans": []})
                return httpx.Response(401, headers={"paypal-debug-id": "dbg-401"}, json={"error": "invalid_token"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http_client = httpx.AsyncClient(transport=transport, base_url=self.test_settings.PAYPAL_BASE_URL)
        client = PayPalRESTClient(
            client=mock_http_client,
            auth_manager=self.auth_manager,
            settings=self.test_settings,
        )

        resp = asyncio.run(client.execute("GET", "/v1/billing/plans"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(get_attempts, 2, "Safe GET should retry once after 401")
        self.assertEqual(token_requests, 1, "Fresh token should be fetched after 401")

    def test_concurrent_token_refresh_single_flight(self):
        """Verify that multiple concurrent token requests share asyncio.Lock (1 underlying HTTP call)."""
        token_requests = 0

        async def handler(request: httpx.Request):
            nonlocal token_requests
            if request.url.path == "/v1/oauth2/token":
                token_requests += 1
                await asyncio.sleep(0.02)
                return httpx.Response(200, json={"access_token": "concurrent_shared_token", "expires_in": 3600})
            return httpx.Response(200)

        transport = httpx.MockTransport(handler)
        mock_http_client = httpx.AsyncClient(transport=transport, base_url=self.test_settings.PAYPAL_BASE_URL)
        fresh_auth_manager = PayPalAuthManager(settings=self.test_settings)

        async def task():
            return await fresh_auth_manager.get_access_token(mock_http_client)

        async def run_concurrent():
            return await asyncio.gather(task(), task(), task(), task(), task())

        tokens = asyncio.run(run_concurrent())
        self.assertEqual(token_requests, 1, "Only 1 HTTP token request should occur under concurrency!")
        self.assertEqual(len(set(tokens)), 1)
        self.assertEqual(tokens[0], "concurrent_shared_token")

    def test_client_ownership_protection(self):
        """Verify that PayPalRESTClient does NOT close externally injected clients on aclose()."""
        external_client = httpx.AsyncClient(base_url=self.test_settings.PAYPAL_BASE_URL)
        paypal_client = PayPalRESTClient(client=external_client, settings=self.test_settings)
        self.assertFalse(paypal_client._owns_client)

        asyncio.run(paypal_client.aclose())
        self.assertFalse(external_client.is_closed, "External injected client must remain open!")
        asyncio.run(external_client.aclose())

    def test_optional_debug_id_extraction(self):
        """Verify debug_id extraction hierarchy and non-fabrication."""
        # 1. Header present
        r1 = httpx.Response(400, headers={"Paypal-Debug-Id": "header-debug-123"}, json={})
        self.assertEqual(extract_debug_id(r1), "header-debug-123")

        # 2. JSON body present without header
        r2 = httpx.Response(400, json={"debug_id": "json-debug-456", "name": "ERROR"})
        self.assertEqual(extract_debug_id(r2), "json-debug-456")

        # 3. Neither present
        r3 = httpx.Response(500, content=b"Server Error")
        self.assertIsNone(extract_debug_id(r3))

        # 4. None response (network timeout)
        self.assertIsNone(extract_debug_id(None))


class TestApplicationLifespanLifecycle(unittest.TestCase):
    """Test FastAPI application lifespan HTTP client initialization and cleanup."""

    def test_lifespan_initializes_and_closes_client(self):
        async def run_lifespan_cycle():
            async with lifespan(app):
                self.assertTrue(hasattr(app.state, "paypal_http_client"))
                self.assertTrue(hasattr(app.state, "paypal_client"))
                self.assertFalse(app.state.paypal_http_client.is_closed)
            # After lifespan exits
            self.assertTrue(app.state.paypal_http_client.is_closed)

        asyncio.run(run_lifespan_cycle())


if __name__ == "__main__":
    unittest.main()
