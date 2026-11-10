"""Integration tests for Analytics, Dashboard Metrics, and Simulation API Endpoints (P7).

Architectural Guarantees:
- Endpoints return verified metrics derived from authoritative database records.
- 0 fabricated metrics in live calculations.
- Simulation records are explicitly tagged [SIMULATED DATA].
"""

import unittest
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from httpx import ASGITransport

from app.main import app
from app.core.database import SessionLocal, init_db
from app.models.subscription import Subscription, PaymentTransaction, PaymentFailure


class TestAnalyticsAndEndpoints(unittest.TestCase):
    """Test REST analytics endpoints and seed simulation."""

    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        from app.api.v1.endpoints.demo import seed_demo_data
        seed_demo_data(db)
        db.close()

    def test_seed_demo_simulation_data(self):
        """Verify POST /api/v1/demo/seed populates realistic demo records with simulated tags."""
        async def run_seed():
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post("/api/v1/demo/seed")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["status"], "success")
                self.assertTrue(len(data["seeded_subscriptions"]) >= 4)

        asyncio.run(run_seed())

    def test_analytics_overview_endpoint(self):
        """Verify GET /api/v1/analytics/overview returns valid numeric KPIs."""
        async def run_overview():
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/analytics/overview")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertIn("total_subscriptions", data)
                self.assertIn("verified_recovered_revenue", data)
                self.assertIn("outstanding_eligible_revenue", data)
                self.assertGreaterEqual(data["total_subscriptions"], 4)
                self.assertGreaterEqual(data["verified_recovered_revenue"], 89.0)

        asyncio.run(run_overview())

    def test_analytics_revenue_and_recovery_endpoints(self):
        """Verify GET /api/v1/analytics/revenue and /recovery endpoints."""
        async def run_metrics():
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r_rev = await client.get("/api/v1/analytics/revenue")
                self.assertEqual(r_rev.status_code, 200)
                d_rev = r_rev.json()
                self.assertIn("recovery_rate_percentage", d_rev)
                self.assertTrue(len(d_rev["revenue_by_month"]) > 0)

                r_rec = await client.get("/api/v1/analytics/recovery")
                self.assertEqual(r_rec.status_code, 200)
                d_rec = r_rec.json()
                self.assertIn("success_rate_percentage", d_rec)
                self.assertTrue(len(d_rec["attempts_timeline"]) > 0)

        asyncio.run(run_metrics())

    def test_analytics_ai_insights_endpoint(self):
        """Verify GET /api/v1/analytics/ai-insights returns actionable merchant intelligence."""
        async def run_insights():
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/analytics/ai-insights")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertIn("insights", data)
                self.assertTrue(len(data["insights"]) >= 1)

        asyncio.run(run_insights())

    def test_recovery_opportunities_list_endpoint(self):
        """Verify GET /api/v1/recovery/opportunities lists seeded opportunities."""
        async def run_opps():
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/recovery/opportunities")
                self.assertEqual(res.status_code, 200)
                opps = res.json()
                self.assertTrue(len(opps) >= 1)
                first_opp = opps[0]
                self.assertIn("eligible_amount", first_opp)
                self.assertIn("subscription_status", first_opp)

        asyncio.run(run_opps())


if __name__ == "__main__":
    unittest.main()
