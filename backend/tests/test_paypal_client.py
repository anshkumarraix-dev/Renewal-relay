"""Comprehensive unit test suite for Renewal Relay PayPal REST client foundation (P0.1).

Covers all 17 requirements:
1. Rejecting PAYPAL_MODE=live.
2. OAuth token acquisition bounded retries.
3. OAuth retry limit exhaustion.
4. OAuth Retry-After numeric and HTTP-date behavior.
5. Safe GET retry on HTTP 502, 503, and 504.
6. Safe GET transient network failure.
7. Safe GET 429 behavior.
8. Mutation timeout and connection-drop ambiguity.
9. Mutation 502, 503, and 504 ambiguity.
10. No automatic mutation retries, including 429.
11. Absolute URL and scheme-relative URL rejection.
12. Malformed request path rejection.
13. Authorization header override protection.
14. Safe-read 401 refresh only once.
15. Concurrent OAuth token refresh.
16. HTTP client ownership protection.
17. FastAPI lifespan cleanup on normal shutdown and exception.
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

from app.core.config import Settings, validate_sandbox_url
from app.core.paypal import (
    PayPalRESTClient,
    PayPalAuthManager,
    OperationSafety,
    classify_operation_safety,
    validate_api_path,
    parse_retry_after,
    extract_debug_id,
    PayPalClientError,
    PayPalAuthError,
    PayPalRateLimitError,
    PayPalTransientError,
    PayPalBusinessError,
    PayPalAmbiguousError,
)
from app.main import app, lifespan


class TestConfigurationAndUrlSecurity(unittest.TestCase):
    """Tests 1, 11, 12: Configuration boundaries, sandbox mode, and URL path validation."""

    def test_reject_paypal_mode_live(self):
        """1. Verify PAYPAL_MODE accepts only 'sandbox' (case-insensitive) and rejects 'live' and others."""
        # Valid sandbox variations
        s1 = Settings(PAYPAL_MODE="sandbox")
        self.assertEqual(s1.PAYPAL_MODE, "sandbox")
        s2 = Settings(PAYPAL_MODE="SANDBOX")
        self.assertEqual(s2.PAYPAL_MODE, "sandbox")
        s3 = Settings(PAYPAL_MODE="  Sandbox  ")
        self.assertEqual(s3.PAYPAL_MODE, "sandbox")

        # Reject live mode explicitly
        with self.assertRaises(ValueError) as ctx:
            Settings(PAYPAL_MODE="live")
        self.assertIn("Live mode is strictly prohibited", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            Settings(PAYPAL_MODE="LIVE")
        self.assertIn("Live mode is strictly prohibited", str(ctx.exception))

        # Reject other modes
        with self.assertRaises(ValueError):
            Settings(PAYPAL_MODE="production")
        with self.assertRaises(ValueError):
            Settings(PAYPAL_MODE="test")

    def test_strict_sandbox_url_validator(self):
        """Verify validate_sandbox_url enforces exact sandbox host and HTTPS."""
        self.assertEqual(
            validate_sandbox_url("https://api-m.sandbox.paypal.com"),
            "https://api-m.sandbox.paypal.com",
        )
        # Rejects Live, non-HTTPS, credentials, alternate hosts, custom ports, paths
        with self.assertRaises(ValueError):
            validate_sandbox_url("https://api-m.paypal.com")
        with self.assertRaises(ValueError):
            validate_sandbox_url("http://api-m.sandbox.paypal.com")
        with self.assertRaises(ValueError):
            validate_sandbox_url("https://user:pass@api-m.sandbox.paypal.com")
        with self.assertRaises(ValueError):
            validate_sandbox_url("https://evil.sandbox.paypal.com")
        with self.assertRaises(ValueError):
            validate_sandbox_url("https://api-m.sandbox.paypal.com:8443")
        with self.assertRaises(ValueError):
            validate_sandbox_url("https://api-m.sandbox.paypal.com/v1")
        with self.assertRaises(ValueError):
            validate_sandbox_url("https://api-m.sandbox.paypal.com?query=1")

    def test_reject_absolute_and_scheme_relative_urls(self):
        """11. Verify execute() rejects absolute URLs and scheme-relative URLs."""
        settings = Settings(
            PAYPAL_CLIENT_ID="id",
            PAYPAL_CLIENT_SECRET="secret",
            PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com",
        )
        client = PayPalRESTClient(settings=settings)

        # Absolute URLs
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(client.execute("GET", "https://api-m.sandbox.paypal.com/v1/billing/plans"))
        self.assertIn("Absolute URLs are strictly prohibited", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(client.execute("GET", "http://evil.com/v1/billing/plans"))
        self.assertIn("Absolute URLs are strictly prohibited", str(ctx.exception))

        # Scheme-relative URLs
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(client.execute("GET", "//evil.com/v1/billing/plans"))
        self.assertIn("Scheme-relative paths are strictly prohibited", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(client.execute("GET", "\\\\evil.com\\v1\\billing\\plans"))
        self.assertIn("Scheme-relative paths are strictly prohibited", str(ctx.exception))

    def test_reject_malformed_request_paths(self):
        """12. Verify execute() rejects paths with embedded query strings, fragments, or empty values."""
        settings = Settings(
            PAYPAL_CLIENT_ID="id",
            PAYPAL_CLIENT_SECRET="secret",
            PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com",
        )
        client = PayPalRESTClient(settings=settings)

        # Query strings prohibited in path (must use 'params')
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(client.execute("GET", "/v1/billing/subscriptions?status=ACTIVE"))
        self.assertIn("Embedded query strings in path are prohibited", str(ctx.exception))

        # Fragments prohibited
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(client.execute("GET", "/v1/billing/subscriptions#details"))
        self.assertIn("URL fragments in path are prohibited", str(ctx.exception))

        # Empty or whitespace paths prohibited
        with self.assertRaises(ValueError):
            asyncio.run(client.execute("GET", ""))
        with self.assertRaises(ValueError):
            asyncio.run(client.execute("GET", "   "))


class TestOAuthTokenAcquisition(unittest.TestCase):
    """Tests 2, 3, 4, 15: OAuth 2.0 token acquisition retries, ceilings, and single-flight lock."""

    def test_oauth_token_acquisition_bounded_retries(self):
        """2. Verify OAuth token acquisition retries on transient failures and succeeds within limit."""
        settings = Settings(
            PAYPAL_CLIENT_ID="test_client_id",
            PAYPAL_CLIENT_SECRET="test_client_secret",
            PAYPAL_MAX_RETRIES=3,
            PAYPAL_BACKOFF_FACTOR=0.01,
        )

        attempts = 0
        sleep_durations = []

        async def mock_sleeper(duration: float):
            sleep_durations.append(duration)

        def mock_handler(request: httpx.Request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, headers={"paypal-debug-id": "dbg-503-auth"})
            return httpx.Response(200, json={"access_token": "fresh_token_123", "expires_in": 3600})

        transport = httpx.MockTransport(mock_handler)
        auth_mgr = PayPalAuthManager(settings=settings, sleeper=mock_sleeper, jitter_func=lambda a, b: b)

        async def run_test():
            async with httpx.AsyncClient(transport=transport, base_url=settings.PAYPAL_BASE_URL) as http_client:
                token = await auth_mgr.get_access_token(http_client)
                self.assertEqual(token, "fresh_token_123")

        asyncio.run(run_test())
        self.assertEqual(attempts, 2)
        self.assertEqual(len(sleep_durations), 1)

    def test_oauth_retry_limit_exhaustion(self):
        """3. Verify OAuth token acquisition aborts with PayPalTransientError when retries are exhausted."""
        settings = Settings(
            PAYPAL_CLIENT_ID="test_client_id",
            PAYPAL_CLIENT_SECRET="test_client_secret",
            PAYPAL_MAX_RETRIES=2,
            PAYPAL_BACKOFF_FACTOR=0.01,
        )

        attempts = 0

        def mock_handler(request: httpx.Request):
            nonlocal attempts
            attempts += 1
            return httpx.Response(502, headers={"paypal-debug-id": "dbg-502-exhaust"})

        transport = httpx.MockTransport(mock_handler)
        auth_mgr = PayPalAuthManager(
            settings=settings,
            sleeper=AsyncMock(),
            jitter_func=lambda a, b: 0.001,
        )

        async def run_test():
            async with httpx.AsyncClient(transport=transport, base_url=settings.PAYPAL_BASE_URL) as http_client:
                with self.assertRaises(PayPalTransientError) as ctx:
                    await auth_mgr.get_access_token(http_client)
                self.assertEqual(ctx.exception.status_code, 502)
                self.assertEqual(ctx.exception.debug_id, "dbg-502-exhaust")

        asyncio.run(run_test())
        self.assertEqual(attempts, 3)  # 1 initial + 2 retries

    def test_oauth_retry_after_numeric_and_http_date(self):
        """4. Verify OAuth Retry-After handles numeric seconds, HTTP-date, and enforces ceiling."""
        settings = Settings(
            PAYPAL_CLIENT_ID="test_client_id",
            PAYPAL_CLIENT_SECRET="test_client_secret",
            PAYPAL_MAX_RETRIES=3,
            PAYPAL_MAX_RETRY_AFTER_SECONDS=10.0,
        )

        # 4a. Numeric Retry-After within ceiling succeeds on retry
        attempts = 0
        sleep_durations = []

        async def mock_sleeper(duration: float):
            sleep_durations.append(duration)

        def numeric_handler(request: httpx.Request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"retry-after": "2.5", "paypal-debug-id": "dbg-429-num"})
            return httpx.Response(200, json={"access_token": "token_after_429", "expires_in": 3600})

        auth_mgr_num = PayPalAuthManager(settings=settings, sleeper=mock_sleeper)

        async def run_num():
            async with httpx.AsyncClient(transport=httpx.MockTransport(numeric_handler), base_url=settings.PAYPAL_BASE_URL) as c:
                token = await auth_mgr_num.get_access_token(c)
                self.assertEqual(token, "token_after_429")

        asyncio.run(run_num())
        self.assertEqual(attempts, 2)
        self.assertEqual(sleep_durations, [2.5])

        # 4b. Numeric Retry-After exceeding ceiling aborts immediately with PayPalRateLimitError
        def ceiling_handler(request: httpx.Request):
            return httpx.Response(429, headers={"retry-after": "60", "paypal-debug-id": "dbg-ceiling"})

        auth_mgr_ceil = PayPalAuthManager(settings=settings, sleeper=AsyncMock())

        async def run_ceil():
            async with httpx.AsyncClient(transport=httpx.MockTransport(ceiling_handler), base_url=settings.PAYPAL_BASE_URL) as c:
                with self.assertRaises(PayPalRateLimitError) as ctx:
                    await auth_mgr_ceil.get_access_token(c)
                self.assertIn("exceeds configured ceiling", str(ctx.exception))
                self.assertEqual(ctx.exception.retry_after, 60.0)

        asyncio.run(run_ceil())

        # 4c. HTTP-date Retry-After parsed and respected
        future_date = email.utils.format_datetime(datetime.now(timezone.utc) + timedelta(seconds=4))
        attempts_date = 0
        sleep_date_durations = []

        async def sleeper_date(dur: float):
            sleep_date_durations.append(dur)

        def date_handler(request: httpx.Request):
            nonlocal attempts_date
            attempts_date += 1
            if attempts_date == 1:
                return httpx.Response(429, headers={"retry-after": future_date, "paypal-debug-id": "dbg-date"})
            return httpx.Response(200, json={"access_token": "token_after_date", "expires_in": 3600})

        auth_mgr_date = PayPalAuthManager(settings=settings, sleeper=sleeper_date)

        async def run_date():
            async with httpx.AsyncClient(transport=httpx.MockTransport(date_handler), base_url=settings.PAYPAL_BASE_URL) as c:
                token = await auth_mgr_date.get_access_token(c)
                self.assertEqual(token, "token_after_date")

        asyncio.run(run_date())
        self.assertEqual(attempts_date, 2)
        self.assertTrue(1.0 <= sleep_date_durations[0] <= 5.0)

    def test_concurrent_oauth_token_refresh(self):
        """15. Verify concurrent token requests share asyncio.Lock (single-flight execution)."""
        settings = Settings(
            PAYPAL_CLIENT_ID="client_id",
            PAYPAL_CLIENT_SECRET="client_secret",
        )
        token_calls = 0

        def handler(request: httpx.Request):
            nonlocal token_calls
            if request.url.path == "/v1/oauth2/token":
                token_calls += 1
                return httpx.Response(200, json={"access_token": "shared_lock_token", "expires_in": 3600})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        auth_mgr = PayPalAuthManager(settings=settings)

        async def run_test():
            async with httpx.AsyncClient(transport=transport, base_url=settings.PAYPAL_BASE_URL) as client:
                results = await asyncio.gather(
                    auth_mgr.get_access_token(client),
                    auth_mgr.get_access_token(client),
                    auth_mgr.get_access_token(client),
                    auth_mgr.get_access_token(client),
                    auth_mgr.get_access_token(client),
                )
                self.assertEqual(len(set(results)), 1)
                self.assertEqual(results[0], "shared_lock_token")

        asyncio.run(run_test())
        self.assertEqual(token_calls, 1)


class TestSafeReadOperations(unittest.TestCase):
    """Tests 5, 6, 7, 13, 14: Safe GET retries on transient errors, 429 ceiling, auth headers, and 401 refresh."""

    def setUp(self):
        self.settings = Settings(
            PAYPAL_CLIENT_ID="id",
            PAYPAL_CLIENT_SECRET="secret",
            PAYPAL_MAX_RETRIES=3,
            PAYPAL_BACKOFF_FACTOR=0.01,
            PAYPAL_MAX_RETRY_AFTER_SECONDS=10.0,
        )

    def test_safe_get_retry_on_502_503_504(self):
        """5. Verify SAFE_READ GET retries on HTTP 502, 503, and 504 and succeeds within limit."""
        attempts = 0
        slept = []

        async def mock_sleeper(d):
            slept.append(d)

        def handler(request: httpx.Request):
            nonlocal attempts
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            attempts += 1
            if attempts == 1:
                return httpx.Response(502, headers={"paypal-debug-id": "dbg-502"})
            elif attempts == 2:
                return httpx.Response(503, headers={"paypal-debug-id": "dbg-503"})
            elif attempts == 3:
                return httpx.Response(504, headers={"paypal-debug-id": "dbg-504"})
            return httpx.Response(200, json={"status": "ACTIVE"})

        transport = httpx.MockTransport(handler)

        async def run_test():
            async with httpx.AsyncClient(transport=transport, base_url=self.settings.PAYPAL_BASE_URL) as hc:
                auth = PayPalAuthManager(settings=self.settings)
                client = PayPalRESTClient(
                    client=hc,
                    auth_manager=auth,
                    settings=self.settings,
                    sleeper=mock_sleeper,
                    jitter_func=lambda a, b: 0.005,
                )
                resp = await client.execute("GET", "/v1/billing/subscriptions/I-123")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["status"], "ACTIVE")

        asyncio.run(run_test())
        self.assertEqual(attempts, 4)  # 1 initial + 3 retries (502, 503, 504 -> 200)
        self.assertEqual(len(slept), 3)

    def test_safe_get_transient_network_failure(self):
        """6. Verify SAFE_READ GET retries on transient connection failure and succeeds on retry."""
        attempts = 0

        def handler(request: httpx.Request):
            nonlocal attempts
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("Simulated TCP connection reset", request=request)
            return httpx.Response(200, json={"status": "CONNECTED"})

        transport = httpx.MockTransport(handler)

        async def run_test():
            async with httpx.AsyncClient(transport=transport, base_url=self.settings.PAYPAL_BASE_URL) as hc:
                auth = PayPalAuthManager(settings=self.settings)
                client = PayPalRESTClient(
                    client=hc,
                    auth_manager=auth,
                    settings=self.settings,
                    sleeper=AsyncMock(),
                    jitter_func=lambda a, b: 0.001,
                )
                resp = await client.execute("GET", "/v1/billing/plans")
                self.assertEqual(resp.status_code, 200)

        asyncio.run(run_test())
        self.assertEqual(attempts, 2)

    def test_safe_get_429_behavior(self):
        """7. Verify SAFE_READ GET honors bounded Retry-After and aborts if ceiling is exceeded."""
        # 7a. Normal Retry-After within ceiling
        attempts = 0
        slept = []

        async def mock_sleeper(d):
            slept.append(d)

        def handler_ok(request: httpx.Request):
            nonlocal attempts
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"retry-after": "1.5", "paypal-debug-id": "dbg-429"})
            return httpx.Response(200, json={"success": True})

        async def run_ok():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler_ok), base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings, sleeper=mock_sleeper)
                resp = await client.execute("GET", "/v1/billing/subscriptions/I-1")
                self.assertEqual(resp.status_code, 200)

        asyncio.run(run_ok())
        self.assertEqual(attempts, 2)
        self.assertEqual(slept, [1.5])

        # 7b. Retry-After exceeding ceiling aborts immediately
        def handler_excessive(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            return httpx.Response(429, headers={"retry-after": "45.0", "paypal-debug-id": "dbg-excess"})

        async def run_excessive():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler_excessive), base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings, sleeper=AsyncMock())
                with self.assertRaises(PayPalRateLimitError) as ctx:
                    await client.execute("GET", "/v1/billing/subscriptions/I-1")
                self.assertIn("exceeds configured ceiling", str(ctx.exception))
                self.assertEqual(ctx.exception.retry_after, 45.0)

        asyncio.run(run_excessive())

    def test_authorization_header_override_protection(self):
        """13. Verify Authorization header cannot be overridden by caller-supplied headers."""
        captured_auth_header = None

        def handler(request: httpx.Request):
            nonlocal captured_auth_header
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "legitimate_access_token", "expires_in": 3600})
            captured_auth_header = request.headers.get("authorization")
            return httpx.Response(200, json={"data": "ok"})

        transport = httpx.MockTransport(handler)

        async def run_test():
            async with httpx.AsyncClient(transport=transport, base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings)
                # Attempt to override Authorization with malicious token
                await client.execute(
                    "GET",
                    "/v1/billing/plans",
                    headers={"Authorization": "Bearer spoofed_token", "authorization": "Bearer spoofed_2"},
                )

        asyncio.run(run_test())
        self.assertEqual(captured_auth_header, "Bearer legitimate_access_token")

    def test_safe_read_401_refresh_only_once(self):
        """14. Verify safe-read 401 triggers token refresh at most once and does not enter infinite loop."""
        api_attempts = 0
        token_attempts = 0

        def handler(request: httpx.Request):
            nonlocal api_attempts, token_attempts
            if request.url.path == "/v1/oauth2/token":
                token_attempts += 1
                return httpx.Response(200, json={"access_token": f"token_v{token_attempts}", "expires_in": 3600})
            api_attempts += 1
            # Continues returning 401
            return httpx.Response(401, headers={"paypal-debug-id": f"dbg-401-{api_attempts}"})

        transport = httpx.MockTransport(handler)

        async def run_test():
            async with httpx.AsyncClient(transport=transport, base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings)
                with self.assertRaises(PayPalAuthError) as ctx:
                    await client.execute("GET", "/v1/billing/plans")
                self.assertEqual(ctx.exception.status_code, 401)
                self.assertEqual(ctx.exception.debug_id, "dbg-401-2")

        asyncio.run(run_test())
        self.assertEqual(api_attempts, 2)  # initial 401 -> refresh -> retry 401 -> abort
        self.assertEqual(token_attempts, 2)


class TestMutationSafetyAndAmbiguity(unittest.TestCase):
    """Tests 8, 9, 10: Zero retries on mutations, timeout/connection-drop ambiguity, and 502/503/504 ambiguity."""

    def setUp(self):
        self.settings = Settings(
            PAYPAL_CLIENT_ID="id",
            PAYPAL_CLIENT_SECRET="secret",
            PAYPAL_MAX_RETRIES=3,
        )

    def test_mutation_timeout_and_connection_drop_ambiguity(self):
        """8. Verify mutation timeouts and connection drops raise PayPalAmbiguousError with preserved request_id."""
        # 8a. Capture timeout -> PayPalAmbiguousError (attempts=1)
        capture_attempts = 0

        def capture_handler(request: httpx.Request):
            nonlocal capture_attempts
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            capture_attempts += 1
            raise httpx.ReadTimeout("Socket timeout waiting for PayPal capture response", request=request)

        async def run_capture():
            async with httpx.AsyncClient(transport=httpx.MockTransport(capture_handler), base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings)
                with self.assertRaises(PayPalAmbiguousError) as ctx:
                    await client.execute(
                        "POST",
                        "/v1/billing/subscriptions/I-789/capture",
                        request_id="capture-req-999",
                    )
                self.assertEqual(ctx.exception.request_id, "capture-req-999")
                self.assertEqual(ctx.exception.operation_safety, OperationSafety.MUTATING_FINANCIAL)
                self.assertIsNone(ctx.exception.debug_id)

        asyncio.run(run_capture())
        self.assertEqual(capture_attempts, 1)  # ZERO automatic retries

        # 8b. Suspend connection drop -> PayPalAmbiguousError (attempts=1)
        suspend_attempts = 0

        def suspend_handler(request: httpx.Request):
            nonlocal suspend_attempts
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
            suspend_attempts += 1
            raise httpx.NetworkError("TCP connection dropped during suspend", request=request)

        async def run_suspend():
            async with httpx.AsyncClient(transport=httpx.MockTransport(suspend_handler), base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings)
                with self.assertRaises(PayPalAmbiguousError) as ctx:
                    await client.execute(
                        "POST",
                        "/v1/billing/subscriptions/I-789/suspend",
                        request_id="suspend-req-111",
                    )
                self.assertEqual(ctx.exception.request_id, "suspend-req-111")
                self.assertEqual(ctx.exception.operation_safety, OperationSafety.MUTATING_SUBSCRIPTION)

        asyncio.run(run_suspend())
        self.assertEqual(suspend_attempts, 1)

    def test_mutation_502_503_504_ambiguity(self):
        """9. Verify mutating operations receiving HTTP 502, 503, or 504 raise PayPalAmbiguousError with preserved details."""
        attempts = {}

        def make_handler(status_code: int, endpoint_name: str):
            attempts[endpoint_name] = 0

            def handler(request: httpx.Request):
                if request.url.path == "/v1/oauth2/token":
                    return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
                attempts[endpoint_name] += 1
                return httpx.Response(status_code, headers={"paypal-debug-id": f"dbg-{status_code}-{endpoint_name}"})

            return handler

        async def run_cases():
            # 502 on capture
            transport_502 = httpx.MockTransport(make_handler(502, "capture"))
            async with httpx.AsyncClient(transport=transport_502, base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings)
                with self.assertRaises(PayPalAmbiguousError) as ctx:
                    await client.execute("POST", "/v1/billing/subscriptions/I-1/capture", request_id="cap-502")
                self.assertEqual(ctx.exception.status_code, 502)
                self.assertEqual(ctx.exception.debug_id, "dbg-502-capture")
                self.assertEqual(ctx.exception.request_id, "cap-502")

            # 503 on suspend
            transport_503 = httpx.MockTransport(make_handler(503, "suspend"))
            async with httpx.AsyncClient(transport=transport_503, base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings)
                with self.assertRaises(PayPalAmbiguousError) as ctx:
                    await client.execute("POST", "/v1/billing/subscriptions/I-1/suspend", request_id="susp-503")
                self.assertEqual(ctx.exception.status_code, 503)
                self.assertEqual(ctx.exception.debug_id, "dbg-503-suspend")

            # 504 on activate
            transport_504 = httpx.MockTransport(make_handler(504, "activate"))
            async with httpx.AsyncClient(transport=transport_504, base_url=self.settings.PAYPAL_BASE_URL) as hc:
                client = PayPalRESTClient(client=hc, settings=self.settings)
                with self.assertRaises(PayPalAmbiguousError) as ctx:
                    await client.execute("POST", "/v1/billing/subscriptions/I-1/activate", request_id="act-504")
                self.assertEqual(ctx.exception.status_code, 504)
                self.assertEqual(ctx.exception.debug_id, "dbg-504-activate")

        asyncio.run(run_cases())
        self.assertEqual(attempts["capture"], 1)
        self.assertEqual(attempts["suspend"], 1)
        self.assertEqual(attempts["activate"], 1)

    def test_no_automatic_mutation_retries_including_429(self):
        """10. Verify mutations (capture, suspend, activate, cancel, revise) NEVER retry automatically on HTTP 429."""
        mutations = [
            ("POST", "/v1/billing/subscriptions/I-1/capture"),
            ("POST", "/v1/billing/subscriptions/I-1/suspend"),
            ("POST", "/v1/billing/subscriptions/I-1/activate"),
            ("POST", "/v1/billing/subscriptions/I-1/cancel"),
            ("POST", "/v1/billing/subscriptions/I-1/revise"),
        ]

        attempt_counts = {}

        for method, path in mutations:
            action = path.split("/")[-1]
            attempt_counts[action] = 0

            def handler(request: httpx.Request, act=action):
                if request.url.path == "/v1/oauth2/token":
                    return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
                attempt_counts[act] += 1
                return httpx.Response(429, headers={"retry-after": "1", "paypal-debug-id": f"dbg-429-{act}"})

            async def run_mutation(m=method, p=path):
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=self.settings.PAYPAL_BASE_URL) as hc:
                    client = PayPalRESTClient(client=hc, settings=self.settings)
                    with self.assertRaises(PayPalRateLimitError):
                        await client.execute(m, p, request_id="req-mutation-429")

            asyncio.run(run_mutation())
            self.assertEqual(attempt_counts[action], 1, f"Expected exactly 1 attempt for {action}")


class TestClientOwnershipAndLifespan(unittest.TestCase):
    """Tests 16, 17: HTTP client ownership protection and FastAPI lifespan cleanup."""

    def test_http_client_ownership_protection(self):
        """16. Verify PayPalRESTClient does NOT close externally injected client on aclose()."""
        external_client = httpx.AsyncClient()

        async def run_test():
            rest_client = PayPalRESTClient(client=external_client)
            await rest_client.aclose()
            # External client must remain OPEN
            self.assertFalse(external_client.is_closed)
            await external_client.aclose()
            self.assertTrue(external_client.is_closed)

        asyncio.run(run_test())

        # When client is internally created, aclose() closes it
        async def run_internal():
            rest_client = PayPalRESTClient()
            self.assertFalse(rest_client.http_client.is_closed)
            await rest_client.aclose()
            self.assertTrue(rest_client.http_client.is_closed)

        asyncio.run(run_internal())

    def test_fastapi_lifespan_cleanup_normal_and_exception(self):
        """17. Verify FastAPI lifespan initializes and cleans up HTTP client on normal shutdown and exception."""
        # 17a. Normal shutdown
        async def run_normal():
            async with lifespan(app):
                self.assertTrue(hasattr(app.state, "paypal_http_client"))
                self.assertFalse(app.state.paypal_http_client.is_closed)
                self.assertIsInstance(app.state.paypal_client, PayPalRESTClient)
                self.assertIsInstance(app.state.paypal_auth_manager, PayPalAuthManager)

            # After exiting lifespan context, client must be closed
            self.assertTrue(app.state.paypal_http_client.is_closed)

        asyncio.run(run_normal())

        # 17b. Exception during lifespan execution (finally block cleanup)
        async def run_exception():
            with self.assertRaises(RuntimeError):
                async with lifespan(app):
                    self.assertFalse(app.state.paypal_http_client.is_closed)
                    raise RuntimeError("Simulated unhandled runtime crash during lifespan")

            # Must still be cleanly closed via finally block
            self.assertTrue(app.state.paypal_http_client.is_closed)

        asyncio.run(run_exception())


if __name__ == "__main__":
    unittest.main()
