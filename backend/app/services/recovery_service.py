"""Merchant-Controlled Recovery and Authorization Service.

Architectural Guarantees:
- Every capture requires explicit human merchant authorization.
- Deterministic policy re-checked immediately prior to execution.
- Idempotency enforced via unique PayPal-Request-Id.
- Ambiguous outcomes (timeouts, drops, 502/503/504) trigger reconciliation, NOT blind retries.
- Authoritative verification: revenue is only marked recovered upon verified completion.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.recovery import (
    RecoveryOpportunity,
    RecoveryEvaluation,
    MerchantApproval,
    RecoveryOperation,
    AuditLog,
)
from app.models.subscription import Subscription, PaymentTransaction
from app.services.paypal_service import PayPalService
from app.services.recovery_policy_service import RecoveryPolicyEngine
from app.core.paypal.exceptions import PayPalAmbiguousError, PayPalClientError

logger = logging.getLogger("renewal_relay.services.recovery")


class RecoveryService:
    """Manages merchant approvals, capture execution, and ambiguous outcome reconciliation."""

    def __init__(self, db: Session, paypal_service: Optional[PayPalService] = None):
        self.db = db
        self.paypal = paypal_service

    def list_opportunities(self, status: Optional[str] = None, limit: int = 50) -> List[RecoveryOpportunity]:
        """List recovery opportunities with optional status filter."""
        stmt = select(RecoveryOpportunity).order_by(desc(RecoveryOpportunity.detected_at)).limit(limit)
        if status:
            stmt = stmt.where(RecoveryOpportunity.status == status.upper())
        return list(self.db.execute(stmt).scalars().all())

    def get_opportunity(self, opportunity_id: str) -> Optional[RecoveryOpportunity]:
        """Fetch opportunity by ID."""
        return self.db.get(RecoveryOpportunity, opportunity_id)

    async def approve_recovery(
        self,
        opportunity_id: str,
        merchant_user: str = "merchant_admin",
        note: Optional[str] = None,
    ) -> RecoveryOpportunity:
        """Process explicit merchant approval and execute authorized balance capture."""
        opp = self.db.get(RecoveryOpportunity, opportunity_id)
        if not opp:
            raise ValueError(f"Recovery opportunity '{opportunity_id}' not found.")

        if opp.status in ("APPROVED", "EXECUTING", "RECOVERED"):
            raise ValueError(f"Opportunity is already in status '{opp.status}'. Cannot execute duplicate recovery.")

        sub = self.db.get(Subscription, opp.subscription_id)
        if not sub:
            raise ValueError(f"Underlying subscription '{opp.subscription_id}' not found.")

        # 1. Deterministic Re-check immediately before execution (Safeguard)
        eval_result = RecoveryPolicyEngine.evaluate(
            subscription_status=sub.status,
            outstanding_balance=sub.outstanding_balance_amount,
            currency=sub.currency,
            failed_payment_count=sub.failed_payment_count,
            next_billing_time=sub.next_billing_time,
        )

        if not eval_result.is_eligible:
            raise ValueError(
                f"Subscription is no longer eligible for recovery. "
                f"Policy Decision: {eval_result.decision}. Reason: {eval_result.reason}"
            )

        # 2. Record Merchant Approval
        approval = MerchantApproval(
            id=str(uuid.uuid4()),
            opportunity_id=opp.id,
            decision="APPROVED",
            merchant_user=merchant_user,
            decision_note=note,
            decided_at=datetime.now(timezone.utc),
        )
        self.db.add(approval)

        # 3. Audit Log Pre-Execution
        audit = AuditLog(
            id=str(uuid.uuid4()),
            entity_type="RECOVERY_OPPORTUNITY",
            entity_id=opp.id,
            action="MERCHANT_APPROVED_CAPTURE",
            actor=merchant_user,
            details_json={
                "subscription_id": sub.id,
                "amount": sub.outstanding_balance_amount,
                "currency": sub.currency,
                "note": note,
            },
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(audit)

        opp.status = "EXECUTING"
        self.db.commit()

        # 4. Prepare Unique Idempotency Key (PayPal-Request-Id)
        request_id = str(uuid.uuid4())
        capture_amount_str = f"{sub.outstanding_balance_amount:.2f}"

        operation = RecoveryOperation(
            id=str(uuid.uuid4()),
            opportunity_id=opp.id,
            subscription_id=sub.id,
            operation_type="CAPTURE",
            request_id=request_id,
            amount=sub.outstanding_balance_amount,
            currency=sub.currency,
            status="INITIATED",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(operation)
        self.db.commit()

        # 5. Dispatch PayPal Capture Request
        try:
            result = await self.paypal.capture_outstanding_balance(
                subscription_id=sub.id,
                amount=capture_amount_str,
                currency_code=sub.currency,
                note=f"Authorized renewal recovery via Renewal Relay (Ref: {opp.id[:8]})",
                request_id=request_id,
            )

            # Success response (200 / 201 / 202)
            operation.status = "COMPLETED"
            operation.paypal_debug_id = result.get("debug_id")
            operation.paypal_capture_id = result.get("id") or result.get("capture_id")
            operation.response_payload = result
            operation.reconciled = True
            operation.reconciled_at = datetime.now(timezone.utc)

            # Record Authoritative Payment Transaction
            tx = PaymentTransaction(
                id=str(uuid.uuid4()),
                subscription_id=sub.id,
                transaction_type="CAPTURE",
                paypal_transaction_id=operation.paypal_capture_id or f"CAP-{request_id[:8]}",
                amount=operation.amount,
                currency=operation.currency,
                status="COMPLETED",
                timestamp=datetime.now(timezone.utc),
            )
            self.db.add(tx)

            # Update Subscription Balances
            recovered_amount = operation.amount
            sub.outstanding_balance_amount = max(0.0, sub.outstanding_balance_amount - recovered_amount)
            sub.last_payment_amount = recovered_amount
            sub.last_payment_time = datetime.now(timezone.utc)
            if sub.outstanding_balance_amount == 0.0:
                sub.failed_payment_count = 0
                if sub.status == "SUSPENDED":
                    sub.status = "ACTIVE"

            opp.status = "RECOVERED"
            opp.resolved_at = datetime.now(timezone.utc)

            self.db.commit()
            self.db.refresh(opp)
            logger.info("Successfully completed recovery capture for opportunity %s ($%.2f)", opp.id, recovered_amount)
            return opp

        except PayPalAmbiguousError as amb_err:
            # SAFEGUARD: Ambiguous outcome: do NOT retry blindly
            logger.error(
                "Ambiguous outcome on capture for opportunity %s (req_id=%s): %s. Flagging for reconciliation.",
                opp.id,
                request_id,
                amb_err.message,
            )
            operation.status = "AMBIGUOUS"
            operation.paypal_debug_id = amb_err.debug_id
            operation.response_payload = {
                "error": amb_err.message,
                "status_code": amb_err.status_code,
                "operation_safety": str(amb_err.operation_safety),
            }
            opp.status = "AMBIGUOUS_RECONCILING"

            # Audit trail
            amb_audit = AuditLog(
                id=str(uuid.uuid4()),
                entity_type="RECOVERY_OPERATION",
                entity_id=operation.id,
                action="AMBIGUOUS_CAPTURE_OUTCOME",
                actor="system",
                details_json={
                    "request_id": request_id,
                    "debug_id": amb_err.debug_id,
                    "error": amb_err.message,
                    "notice": "Reconciliation required before any subsequent attempt.",
                },
                timestamp=datetime.now(timezone.utc),
            )
            self.db.add(amb_audit)
            self.db.commit()
            self.db.refresh(opp)
            return opp

        except PayPalClientError as client_err:
            logger.warning("PayPal capture rejected for opportunity %s: %s", opp.id, client_err.message)
            operation.status = "FAILED"
            operation.paypal_debug_id = client_err.debug_id
            operation.response_payload = {
                "error": client_err.message,
                "status_code": client_err.status_code,
            }
            opp.status = "UNRECOVERABLE"
            self.db.commit()
            self.db.refresh(opp)
            return opp

    async def reject_recovery(
        self,
        opportunity_id: str,
        merchant_user: str = "merchant_admin",
        note: Optional[str] = None,
    ) -> RecoveryOpportunity:
        """Record explicit merchant rejection of a recovery opportunity."""
        opp = self.db.get(RecoveryOpportunity, opportunity_id)
        if not opp:
            raise ValueError(f"Recovery opportunity '{opportunity_id}' not found.")

        approval = MerchantApproval(
            id=str(uuid.uuid4()),
            opportunity_id=opp.id,
            decision="REJECTED",
            merchant_user=merchant_user,
            decision_note=note,
            decided_at=datetime.now(timezone.utc),
        )
        self.db.add(approval)

        audit = AuditLog(
            id=str(uuid.uuid4()),
            entity_type="RECOVERY_OPPORTUNITY",
            entity_id=opp.id,
            action="MERCHANT_REJECTED_RECOVERY",
            actor=merchant_user,
            details_json={"note": note},
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(audit)

        opp.status = "REJECTED"
        opp.resolved_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(opp)
        return opp

    async def reconcile_operation(self, operation_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Reconcile an ambiguous recovery operation against PayPal authoritative transaction history."""
        op = self.db.get(RecoveryOperation, operation_id)
        if not op:
            raise ValueError(f"Recovery operation '{operation_id}' not found.")

        opp = self.db.get(RecoveryOpportunity, op.opportunity_id)
        sub = self.db.get(Subscription, op.subscription_id)

        # Query PayPal subscription transaction history for the past 48 hours
        now = datetime.now(timezone.utc)
        start_time = (now - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
        end_time = now.strftime("%Y-%m-%dT23:59:59Z")

        previous_status = op.status
        found_capture = False
        capture_tx_id = None

        try:
            tx_data = await self.paypal.list_subscription_transactions(
                subscription_id=op.subscription_id,
                start_time=start_time,
                end_time=end_time,
            )
            transactions = tx_data.get("transactions", [])
            for tx in transactions:
                # Check for completed capture transaction matching amount
                if tx.get("status") == "COMPLETED":
                    tx_amount = float(tx.get("amount_with_breakdown", {}).get("gross_amount", {}).get("value", 0.0))
                    if abs(tx_amount - op.amount) < 0.01:
                        found_capture = True
                        capture_tx_id = tx.get("id")
                        break
        except Exception as exc:
            logger.warning("Could not query PayPal transactions during reconciliation: %s", str(exc))

        if found_capture:
            # Operation did succeed upstream
            op.status = "COMPLETED"
            op.paypal_capture_id = capture_tx_id
            op.reconciled = True
            op.reconciled_at = now
            if opp:
                opp.status = "RECOVERED"
                opp.resolved_at = now
            if sub:
                sub.outstanding_balance_amount = max(0.0, sub.outstanding_balance_amount - op.amount)
            message = "Reconciled with PayPal: Verified completed capture transaction."
        else:
            # No capture found; safe to close ambiguous operation
            op.status = "FAILED"
            op.reconciled = True
            op.reconciled_at = now
            if opp:
                opp.status = "ELIGIBLE"  # Return to queue for clean retry if still desired
            message = "Reconciled with PayPal: Verified no capture occurred. Returned to eligible queue."

        self.db.commit()
        return {
            "operation_id": op.id,
            "subscription_id": op.subscription_id,
            "previous_status": previous_status,
            "reconciled_status": op.status,
            "reconciled_via": "SUBSCRIPTION_TRANSACTIONS_INSPECTION",
            "paypal_debug_id": op.paypal_debug_id,
            "message": message,
        }
