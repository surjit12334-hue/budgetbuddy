"""Agent Payment Protocol integration (BudgetBuddy as the *seller*).

Spec (authoritative):
    https://innovationlab.fetch.ai/resources/docs/agent-transaction/agent-payment-protocol

Wire protocol::

    RequestPayment  (seller → buyer)  "here is what to pay, and how"
    CommitPayment   (buyer → seller)  "I paid; here is the transaction id"
    RejectPayment   (buyer → seller)  "I decline"
    CompletePayment (seller → buyer)  "verified and accepted"
    CancelPayment   (seller → buyer)  "abort after commit"

The protocol is *rail agnostic*: ``Funds.payment_method`` says how the
buyer pays, and any rail-specific rendering hints go into
``RequestPayment.metadata``.  Three rails are implemented:

``bb_commit``
    The always-available rail.  The seller puts a random ``challenge``
    in the request metadata; the buyer signs it with its uAgents
    identity key and returns the signature in ``CommitPayment``.  The
    seller verifies that signature against the *sender's agent address*
    (ECDSA secp256k1, the same keypair that produced ``agent1q...``).
    That is a genuine, unforgeable proof of commitment bound to the
    buyer's agent identity — and it needs no external credentials.
    It is a commitment, **not** a value transfer: see the class docstring.

``stripe``
    Real card payment via Stripe embedded Checkout.  The checkout
    payload goes into ``metadata["stripe"]`` (publishable key +
    client secret + session id — never the secret key) and the seller
    verifies ``payment_status == "paid"`` on commit.  This is the
    officially documented, judge-visible path.

``fet_direct``
    Real on-chain payment.  The seller publishes its MultiversX address
    and the buyer broadcasts a transaction; the seller verifies the
    transaction by hash against the chain (status, receiver, value)
    before completing.

The verification step is real in every rail and can FAIL — a failed
verification is answered with ``CancelPayment``, never with a silent
unlock.  That is the contract the whole module exists to honour.
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .models import PaymentRequest

PRO_PRICE = 4.99
PRO_CURRENCY = "USD"
PRO_DESCRIPTION = "BudgetBuddy Pro — Lifetime Access"
PRO_DEADLINE_SECONDS = 900  # 15 minutes to pay

# Payment-method identifiers (conventional strings, per the spec).
RAIL_COMMIT = "bb_commit"
RAIL_STRIPE = "stripe"
RAIL_CHAIN = "fet_direct"

# Metadata key BudgetBuddy uses for its own rail hints.
BB_METADATA_KEY = "bb"

# Chain (MultiversX) endpoints.  Both are reachable in the wild; the
# devnet one is what the demo uses.
CHAIN_APIS = {
    "devnet": "https://devnet-api.multiversx.com",
    "mainnet": "https://api.multiversx.com",
}


# ── verification result ────────────────────────────────────────────────

@dataclass
class VerificationResult:
    """Outcome of checking a ``CommitPayment``."""

    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


# ── rails ──────────────────────────────────────────────────────────────

class PaymentRail:
    """Base class for a payment rail.

    A rail knows three things: how to describe itself in a
    ``RequestPayment``, what to put in the request metadata so a UI can
    render the payment, and how to verify a ``CommitPayment``.
    """

    name = "base"
    currency = PRO_CURRENCY
    amount = PRO_PRICE

    def __init__(self, amount: float = PRO_PRICE, currency: str = PRO_CURRENCY):
        self.amount = amount
        self.currency = currency

    # -- request description --------------------------------------------

    def funds(self) -> "Any":
        """The ``Funds`` the seller accepts for this request."""
        from uagents_core.contrib.protocols.payment import Funds

        return Funds(
            amount=f"{self.amount:.2f}",
            currency=self.currency,
            payment_method=self.name,
        )

    def build_metadata(self, request: PaymentRequest) -> Dict[str, Any]:
        """Rail-specific payload for ``RequestPayment.metadata``."""
        return {}

    # -- verification ----------------------------------------------------

    def verify(
        self,
        *,
        transaction_id: Optional[str],
        funds: Any,
        request: PaymentRequest,
        sender: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Check a commit against this rail.  Must never raise."""
        return VerificationResult(False, "no verification implemented")

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _check_funds(funds: Any, amount: float, currency: str, method: str) -> Optional[str]:
        """Validate the ``Funds`` the buyer committed.  Returns an error
        string, or None when the funds are acceptable."""
        if funds is None:
            return "commit carried no funds"
        if getattr(funds, "payment_method", None) != method:
            return (
                f"unsupported payment method "
                f"{getattr(funds, 'payment_method', None)!r} (expected {method!r})"
            )
        if getattr(funds, "currency", None) != currency:
            return (
                f"wrong currency {getattr(funds, 'currency', None)!r} "
                f"(expected {currency!r})"
            )
        try:
            committed = round(float(getattr(funds, "amount", 0)), 2)
        except (TypeError, ValueError):
            return f"unparseable amount {getattr(funds, 'amount', None)!r}"
        if committed != round(amount, 2):
            return f"wrong amount {committed} (expected {amount})"
        return None


class CommitRail(PaymentRail):
    """Proof-of-commitment rail — works with zero external credentials.

    The buyer signs the seller's per-request ``challenge`` with its
    uAgents identity key.  Because an uAgents ``agent1q...`` address
    *is* the compressed public key of that identity, the seller can
    verify the signature against the address the message came from.
    A buyer cannot be impersonated and a commit cannot be replayed
    against a different request.

    This proves the buyer committed to *this* request.  It is not a
    transfer of value, and the app says so plainly in the chat text.
    """

    name = RAIL_COMMIT

    def build_metadata(self, request: PaymentRequest) -> Dict[str, Any]:
        return {
            BB_METADATA_KEY: {
                "reference": request.reference,
                "challenge": request.challenge,
                "amount": f"{self.amount:.2f}",
                "currency": self.currency,
                "how": (
                    "Sign the challenge with your agent identity and return the "
                    "signature in CommitPayment.metadata['bb']['signature']."
                ),
            }
        }

    def verify(
        self,
        *,
        transaction_id: Optional[str],
        funds: Any,
        request: PaymentRequest,
        sender: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        err = self._check_funds(funds, self.amount, self.currency, self.name)
        if err:
            return VerificationResult(False, err)

        if not transaction_id:
            return VerificationResult(False, "commit carried no transaction id")

        meta = (metadata or {}).get(BB_METADATA_KEY) or {}
        signature = meta.get("signature")
        if not signature:
            return VerificationResult(False, "commit carried no signature")

        if meta.get("reference") != request.reference:
            return VerificationResult(False, "commit reference does not match request")

        ok = verify_commit_signature(sender, request.challenge, signature)
        if not ok:
            return VerificationResult(
                False, "signature does not verify against the sender's agent address"
            )
        return VerificationResult(True, "commitment signature verified")


class StripeRail(PaymentRail):
    """Real card payment through Stripe embedded Checkout.

    Requires ``STRIPE_SECRET_KEY`` and ``STRIPE_PUBLISHABLE_KEY``.  The
    *publishable* key and the checkout session id go into the request
    metadata so a UI can render the checkout; the secret key never
    leaves the agent.
    """

    name = RAIL_STRIPE

    def __init__(self, amount: float = PRO_PRICE, currency: str = PRO_CURRENCY):
        super().__init__(amount, currency.lower())
        self.secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self.publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

    def available(self) -> bool:
        return bool(self.secret_key and self.publishable_key)

    def build_metadata(self, request: PaymentRequest) -> Dict[str, Any]:
        if not self.available():
            return {}
        try:
            import stripe
        except ImportError:
            return {}
        stripe.api_key = self.secret_key
        try:
            session = stripe.checkout.Session.create(
                ui_mode="embedded",
                redirect_on_completion="if_required",
                payment_method_types=["card"],
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": self.currency,
                            "product_data": {
                                "name": "BudgetBuddy Pro",
                                "description": PRO_DESCRIPTION,
                            },
                            "unit_amount": int(round(self.amount * 100)),
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "reference": request.reference,
                    "session_id": request.session_id or "",
                },
            )
        except Exception:
            return {}
        return {
            "stripe": {
                "ui_mode": "embedded",
                "publishable_key": self.publishable_key,
                "client_secret": session.client_secret,
                "checkout_session_id": session.id,
                "currency": self.currency,
                "amount_cents": int(round(self.amount * 100)),
            }
        }

    def verify(
        self,
        *,
        transaction_id: Optional[str],
        funds: Any,
        request: PaymentRequest,
        sender: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        err = self._check_funds(funds, self.amount, self.currency, self.name)
        if err:
            return VerificationResult(False, err)
        if not transaction_id:
            return VerificationResult(False, "commit carried no checkout session id")
        try:
            import stripe
        except ImportError:
            return VerificationResult(False, "stripe library not installed")
        stripe.api_key = self.secret_key
        try:
            session = stripe.checkout.Session.retrieve(transaction_id)
        except Exception as exc:
            return VerificationResult(False, f"stripe lookup failed: {exc}")
        if getattr(session, "payment_status", None) != "paid":
            return VerificationResult(
                False, "stripe session is not marked paid yet — finish checkout and retry"
            )
        return VerificationResult(True, "stripe session marked paid")


class ChainRail(PaymentRail):
    """Real on-chain payment, verified against the MultiversX chain.

    The seller publishes its chain address; the buyer broadcasts a
    transfer and returns the transaction hash.  The seller then asks the
    chain whether that transaction succeeded, whether it paid the
    seller's address, and whether it carried enough value.
    """

    name = RAIL_CHAIN

    def __init__(self, amount: float = PRO_PRICE, currency: str = PRO_CURRENCY):
        super().__init__(amount, currency)
        self.network = os.environ.get("PAYMENT_NETWORK", "devnet")
        self.recipient = os.environ.get("AGENT_WALLET_ADDRESS", "")
        self.api = CHAIN_APIS.get(self.network, CHAIN_APIS["devnet"])

    def available(self) -> bool:
        return bool(self.recipient)

    def _atomic(self) -> int:
        # EGLD has 18 decimals.
        return int(round(self.amount * 10**18))

    def build_metadata(self, request: PaymentRequest) -> Dict[str, Any]:
        if not self.available():
            return {}
        return {
            "fet": {
                "network": self.network,
                "recipient": self.recipient,
                "currency": "EGLD",
                "amount": f"{self.amount:.2f}",
                "amount_atomic": str(self._atomic()),
                "reference": request.reference,
            }
        }

    def verify(
        self,
        *,
        transaction_id: Optional[str],
        funds: Any,
        request: PaymentRequest,
        sender: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        err = self._check_funds(funds, self.amount, self.currency, self.name)
        if err:
            return VerificationResult(False, err)
        if not transaction_id:
            return VerificationResult(False, "commit carried no transaction hash")
        if not self.available():
            return VerificationResult(False, "no AGENT_WALLET_ADDRESS configured")

        tx = self._fetch_transaction(transaction_id)
        if tx is None:
            return VerificationResult(
                False, f"transaction {transaction_id[:16]}… not found on {self.network}"
            )
        if tx.get("status") != "success":
            return VerificationResult(
                False, f"transaction status is {tx.get('status')!r}, not 'success'"
            )
        if tx.get("receiver") != self.recipient:
            return VerificationResult(False, "transaction paid a different address")
        try:
            value = int(tx.get("value", "0"))
        except (TypeError, ValueError):
            return VerificationResult(False, "unparseable transaction value")
        if value < self._atomic():
            return VerificationResult(
                False, f"transaction value {value} is below the required {self._atomic()}"
            )
        return VerificationResult(True, f"transaction {transaction_id[:16]}… verified on chain")

    def _fetch_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        import requests

        try:
            resp = requests.get(
                f"{self.api}/transactions/{tx_hash}",
                headers={"User-Agent": "budgetbuddy/1.0"},
                timeout=15,
            )
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None


# ── signature helpers ──────────────────────────────────────────────────

def commitment_digest(challenge: str) -> bytes:
    """Digest a challenge string into something signable."""
    return hashlib.sha256(challenge.encode("utf-8")).digest()


def sign_commitment(challenge: str, identity) -> str:
    """Sign a challenge with a uAgents ``Identity``.

    ``sign_digest``/``verify_digest`` are uAgents' own matched pair, so
    the signature is a bech32 ``sig1…`` string that any uAgents
    identity can verify.
    """
    return identity.sign_digest(commitment_digest(challenge))


def verify_commit_signature(address: str, challenge: str, signature: str) -> bool:
    """Verify a commitment signature against an agent address.

    The uAgents agent address *is* the compressed ECDSA public key of
    the identity, so no extra key exchange is needed: whoever sends the
    commit is the only party who can have produced a valid signature.
    """
    try:
        from uagents_core.identity import Identity

        return Identity.verify_digest(
            address, commitment_digest(challenge), signature
        )
    except Exception:
        return False


# ── manager ────────────────────────────────────────────────────────────

class PaymentManager:
    """Tracks payment requests and their state.

    Requests are keyed by id and also indexed by session, so the Pro
    unlock can be tied to the conversation that paid for it.
    """

    def __init__(self):
        self._requests: Dict[str, PaymentRequest] = {}

    # -- lifecycle -------------------------------------------------------

    def create_pro_request(
        self,
        session_id: str = "",
        buyer: str = "",
        rail: str = "",
    ) -> PaymentRequest:
        req_id = uuid.uuid4().hex[:8]
        req = PaymentRequest(
            id=req_id,
            amount=PRO_PRICE,
            currency=PRO_CURRENCY,
            description=PRO_DESCRIPTION,
            session_id=session_id,
            buyer=buyer,
            rail=rail or self.default_rail(),
            reference=uuid.uuid4().hex,
            challenge=uuid.uuid4().hex + uuid.uuid4().hex,
            expires_at=datetime.now() + timedelta(seconds=PRO_DEADLINE_SECONDS),
        )
        self._requests[req_id] = req
        return req

    def get_request(self, request_id: str) -> Optional[PaymentRequest]:
        return self._requests.get(request_id)

    def all_requests(self) -> List[PaymentRequest]:
        return list(self._requests.values())

    def request_for_buyer(self, buyer: str) -> Optional[PaymentRequest]:
        """Most recent live request aimed at a given buyer address."""
        if not buyer:
            return None
        live = [
            r for r in self._requests.values()
            if r.buyer == buyer and r.status == "pending"
        ]
        if not live:
            return None
        return max(live, key=lambda r: r.created_at)

    def request_for_session(self, session_id: str) -> Optional[PaymentRequest]:
        """Most recent live request for a session."""
        live = [
            r for r in self._requests.values()
            if r.session_id == session_id and r.status == "pending"
        ]
        if not live:
            return None
        return max(live, key=lambda r: r.created_at)

    def mark_paid(self, request_id: str, transaction_id: str = "") -> bool:
        req = self._requests.get(request_id)
        if req and req.status == "pending":
            req.status = "paid"
            req.paid_at = datetime.now()
            req.transaction_id = transaction_id
            return True
        return False

    def cancel_request(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        if req and req.status == "pending":
            req.status = "cancelled"
            return True
        return False

    def is_pro(self, request_id: str) -> bool:
        """True when the given request was paid."""
        req = self._requests.get(request_id)
        return bool(req and req.status == "paid")

    def is_paid(self, request_id: str) -> bool:
        return self.is_pro(request_id)

    # -- rails ------------------------------------------------------------

    def default_rail(self) -> str:
        """Pick the best available rail.

        ``auto`` prefers a rail that can move real money, and falls
        back to the credential-free commitment rail.
        """
        configured = os.environ.get("PAYMENT_RAIL", "auto").lower()
        if configured != "auto":
            return configured
        if StripeRail().available():
            return RAIL_STRIPE
        if ChainRail().available():
            return RAIL_CHAIN
        return RAIL_COMMIT

    def rail_for(self, name: str) -> PaymentRail:
        if name == RAIL_STRIPE:
            return StripeRail()
        if name == RAIL_CHAIN:
            return ChainRail()
        return CommitRail()

    # -- protocol glue ----------------------------------------------------

    def build_request_payment(self, request: PaymentRequest):
        """Build the protocol ``RequestPayment`` for a request."""
        from uagents_core.contrib.protocols.payment import RequestPayment

        rail = self.rail_for(request.rail)
        metadata = rail.build_metadata(request) or {}
        metadata[BB_METADATA_KEY] = {
            **metadata.get(BB_METADATA_KEY, {}),
            "reference": request.reference,
            "challenge": request.challenge,
            "amount": f"{request.amount:.2f}",
            "currency": request.currency,
            "rail": request.rail,
        }
        return RequestPayment(
            accepted_funds=[rail.funds()],
            recipient=request.recipient,
            deadline_seconds=PRO_DEADLINE_SECONDS,
            reference=request.reference,
            description=request.description,
            metadata=metadata,
        )

    def verify_commit(
        self,
        *,
        request: PaymentRequest,
        sender: str,
        funds: Any,
        transaction_id: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify a commit against the request's rail."""
        if request.status != "pending":
            return VerificationResult(False, f"request is {request.status}")
        if request.expires_at and datetime.now() > request.expires_at:
            return VerificationResult(False, "request has expired")
        rail = self.rail_for(request.rail)
        return rail.verify(
            transaction_id=transaction_id,
            funds=funds,
            request=request,
            sender=sender,
            metadata=metadata,
        )

    # -- formatting --------------------------------------------------------

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
