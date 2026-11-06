"""Foundation test suite for Renewal Relay backend.

Validates:
1. Application health endpoint logic and status separation
2. Successful database connectivity (real SQLite via SQLAlchemy)
3. Database failure handling (HTTP 503 and degraded status)
4. Configuration loading and safe security defaults
5. Application route and middleware wiring
"""

import os
import sys
import unittest
from unittest.mock import MagicMock
from fastapi import Response
from sqlalchemy.exc import OperationalError

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.core.config import Settings
from app.core.database import SessionLocal, check_database_health
from app.api.v1.endpoints.health import get_health, get_liveness


class TestConfiguration(unittest.TestCase):
    """Test configuration loading, validation, and safe defaults."""

    def test_safe_defaults(self):
        settings = Settings()
        self.assertEqual(settings.ENVIRONMENT, "development")
        self.assertEqual(settings.PAYPAL_MODE, "sandbox")
        self.assertTrue(settings.ENFORCE_DETERMINISTIC_POLICY)
        self.assertFalse(settings.ALLOW_AI_AUTONOMOUS_PAYMENT)
        self.assertIn("http://localhost:5173", settings.CORS_ORIGINS)

    def test_cors_wildcard_rejection(self):
        with self.assertRaises(ValueError):
            Settings(CORS_ORIGINS=["*"])

    def test_paypal_mode_validation(self):
        with self.assertRaises(ValueError):
            Settings(PAYPAL_MODE="invalid_mode")

    def test_sanitized_dict_masks_secrets(self):
        settings = Settings(
            PAYPAL_CLIENT_ID="sandbox_client_id_abc123",
            PAYPAL_CLIENT_SECRET="sandbox_secret_xyz789",
        )
        sanitized = settings.sanitized_dict()
        self.assertNotIn("sandbox_secret_xyz789", str(sanitized))
        self.assertIn("***REDACTED", sanitized["PAYPAL_CLIENT_SECRET"])


class TestDatabaseConnectivity(unittest.TestCase):
    """Test database connectivity helper directly using real SQLite and simulated failure."""

    def test_check_database_health_success(self):
        is_connected, latency, error = check_database_health()
        self.assertTrue(is_connected, "Database health check should return connected=True")
        self.assertGreaterEqual(latency, 0.0)
        self.assertIsNone(error)

    def test_check_database_health_failure(self):
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("Simulated DB timeout")
        is_connected, latency, error = check_database_health(session=mock_session)
        self.assertFalse(is_connected, "Database health check should return connected=False on error")
        self.assertIn("Simulated DB timeout", error)


class TestHealthEndpoint(unittest.TestCase):
    """Test health check endpoints with separate app and database status models."""

    def test_liveness_endpoint(self):
        result = get_liveness()
        self.assertEqual(result["status"], "alive")
        self.assertIn("timestamp", result)

    def test_health_success(self):
        """Verify real SQLite database check returns operational status and 200."""
        db = SessionLocal()
        response = Response()
        try:
            result = get_health(response=response, db=db)
            self.assertEqual(result.status, "healthy")
            self.assertEqual(result.environment, "development")

            # Verify separated component statuses
            self.assertEqual(result.app.status, "operational")
            self.assertEqual(result.database.status, "operational")
            self.assertIsNotNone(result.database.latency_ms)

            # Verify PayPal Sandbox isolation (no external polling)
            self.assertEqual(result.paypal["mode"], "sandbox")
            self.assertFalse(result.paypal["external_polling"])

            # Verify governance boundaries
            self.assertTrue(result.governance["deterministic_policy_enforced"])
            self.assertFalse(result.governance["ai_autonomous_payment_allowed"])
            self.assertEqual(result.governance["payment_authority"], "PayPal")
        finally:
            db.close()

    def test_database_failure_handling(self):
        """Simulate database disconnection and verify degraded status + HTTP 503."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = OperationalError("Simulated connection dropped", {}, None)
        response = Response()

        result = get_health(response=response, db=mock_db)

        # HTTP status code must be 503 Service Unavailable
        self.assertEqual(response.status_code, 503)

        # Status must be degraded
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.app.status, "operational")
        self.assertEqual(result.database.status, "error")
        self.assertIn("OperationalError", result.database.message)


class TestAppWiring(unittest.TestCase):
    """Test application routing and middleware configuration."""

    def test_registered_routes(self):
        openapi_paths = list(app.openapi()["paths"].keys())
        self.assertIn("/api/v1/health", openapi_paths)
        self.assertIn("/api/v1/health/live", openapi_paths)

    def test_cors_middleware_configured(self):
        # Verify middleware exists
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        self.assertIn("CORSMiddleware", middleware_classes)


if __name__ == "__main__":
    unittest.main()
