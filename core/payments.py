"""Payment request lifecycle (mock now, testnet-ready interface)."""

import uuid
from datetime import datetime
from typing import Optional, Dict

from .models import PaymentRequest

PRO_PRICE = 4.99
PRO_CURRENCY = "USD"
PRO_DESCRIPTION = "BudgetBuddy Pro — Lifetime Access"


class PaymentManager:
    def __init__(self):
        self._requests: Dict[str, PaymentRequest] = {}

    # ── lifecycle ──────────────────────────────────────────────────────

    def create_pro_request(self) -> PaymentRequest:
        req_id = uuid.uuid4().hex[:8]
        req = PaymentRequest(
            id=req_id,
            amount=PRO_PRICE,
            currency=PRO_CURRENCY,
            description=PRO_DESCRIPTION,
        )
        self._requests[req_id] = req
        return req

    def get_request(self, request_id: str) -> Optional[PaymentRequest]:
        return self._requests.get(request_id)

    def mark_paid(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        if req and req.status == "pending":
            req.status = "paid"
            req.paid_at = datetime.now()
            return True
        return False

    def cancel_request(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        if req and req.status == "pending":
            req.status = "cancelled"
            return True
        return False

    def is_pro(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        return bool(req and req.status == "paid")

    # ── formatting ─────────────────────────────────────────────────────

    @staticmethod
    def format_request(req: PaymentRequest) -> str:
        return (
            "═══ Payment Request ═══\n\n"
            f"📦 {req.description}\n"
            f"💰 Amount: ${req.amount:.2f} {req.currency}\n"
            f"🆔 Request ID: {req.id}\n"
            f"📝 Status: {req.status.upper()}\n\n"
            "To complete payment, use the ASI:One payment protocol\n"
            "or the testnet faucet."
        )
