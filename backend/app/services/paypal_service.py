"""PayPal REST API Service Layer.

Provides application-level operations over the resilient PayPalRESTClient:
- Subscription inspection and billing cycle retrieval
- Billing plan retrieval
- Subscription transaction history queries
- Outstanding balance capture with strict idempotency (PayPal-Request-Id)
- Webhook signature verification via PayPal's official verification endpoint
"""

import logging
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.core.paypal.client import PayPalRESTClient, OperationSafety
from app.core.paypal.exceptions import PayPalClientError, PayPalAmbiguousError

logger = logging.getLogger("renewal_relay.services.paypal")


class PayPalService:
    """Service wrapping PayPal REST API endpoints with domain operations."""

    def __init__(self, rest_client: PayPalRESTClient):
        self._client = rest_client

    async def get_plan_details(self, plan_id: str) -> Dict[str, Any]:
        """Retrieve details for a specific billing plan.
        GET /v1/billing/plans/{plan_id}
        """
        response = await self._client.execute(
            method="GET",
            path=f"/v1/billing/plans/{plan_id}",
            declared_safety=OperationSafety.SAFE_READ,
        )
        return response.json()

    async def list_plans(self, page_size: int = 20, page: int = 1) -> Dict[str, Any]:
        """List billing plans.
        GET /v1/billing/plans
        """
        response = await self._client.execute(
            method="GET",
            path="/v1/billing/plans",
            params={"page_size": page_size, "page": page, "total_required": "true"},
            declared_safety=OperationSafety.SAFE_READ,
        )
        return response.json()

    async def get_subscription_details(self, subscription_id: str) -> Dict[str, Any]:
        """Retrieve subscription details including status, outstanding balance, and billing info.
        GET /v1/billing/subscriptions/{subscription_id}
        """
        response = await self._client.execute(
            method="GET",
            path=f"/v1/billing/subscriptions/{subscription_id}",
            declared_safety=OperationSafety.SAFE_READ,
        )
        return response.json()

    async def list_subscription_transactions(
        self,
        subscription_id: str,
        start_time: str,
        end_time: str,
    ) -> Dict[str, Any]:
        """Retrieve transaction history for a subscription within a date range.
        GET /v1/billing/subscriptions/{subscription_id}/transactions
        """
        response = await self._client.execute(
            method="GET",
            path=f"/v1/billing/subscriptions/{subscription_id}/transactions",
            params={"start_time": start_time, "end_time": end_time},
            declared_safety=OperationSafety.SAFE_READ,
        )
        return response.json()

    async def capture_outstanding_balance(
        self,
        subscription_id: str,
        amount: str,
        currency_code: str,
        note: str,
        request_id: str,
    ) -> Dict[str, Any]:
        """Capture an outstanding balance on an eligible subscription.
        POST /v1/billing/subscriptions/{subscription_id}/capture

        Strict Safety:
        - Passed request_id is pinned as PayPal-Request-Id (idempotency).
        - Ambiguous transport outcomes (timeouts, network drops, 502/503/504) raise PayPalAmbiguousError.
        - ZERO blind retries are executed by the client.
        """
        payload = {
            "note": note,
            "capture_type": "OUTSTANDING_BALANCE",
            "amount": {
                "currency_code": currency_code,
                "value": str(amount),
            },
        }

        logger.info(
            "Executing PayPal capture for subscription %s: amount=%s %s (request_id=%s)",
            subscription_id,
            amount,
            currency_code,
            request_id,
        )

        response = await self._client.execute(
            method="POST",
            path=f"/v1/billing/subscriptions/{subscription_id}/capture",
            data=payload,
            request_id=request_id,
            declared_safety=OperationSafety.MUTATING_FINANCIAL,
        )

        # PayPal returns HTTP 202 Accepted or 200 OK or 204 No Content
        if response.status_code in (200, 201, 202):
            try:
                return response.json()
            except Exception:
                return {
                    "status": "ACCEPTED",
                    "status_code": response.status_code,
                    "debug_id": response.headers.get("paypal-debug-id"),
                }

        return {
            "status": "COMPLETED" if response.status_code == 204 else "ACCEPTED",
            "status_code": response.status_code,
            "debug_id": response.headers.get("paypal-debug-id"),
        }

    async def verify_webhook_signature(
        self,
        auth_algo: str,
        cert_url: str,
        transmission_id: str,
        transmission_sig: str,
        transmission_time: str,
        webhook_id: str,
        webhook_event: Dict[str, Any],
    ) -> bool:
        """Verify the cryptographic signature of an inbound webhook event via PayPal REST API.
        POST /v1/notifications/verify-webhook-signature
        """
        verify_payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": webhook_event,
        }

        try:
            response = await self._client.execute(
                method="POST",
                path="/v1/notifications/verify-webhook-signature",
                data=verify_payload,
                declared_safety=OperationSafety.SAFE_READ,  # Verification check is idempotent and non-financial
            )
            result = response.json()
            status = result.get("verification_status", "").upper()
            is_valid = status == "SUCCESS"
            if not is_valid:
                logger.warning(
                    "PayPal webhook signature verification returned status '%s' for transmission_id=%s",
                    status,
                    transmission_id,
                )
            return is_valid
        except Exception as exc:
            logger.error("Error verifying PayPal webhook signature: %s", str(exc))
            return False
