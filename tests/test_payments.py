#!/usr/bin/env python3
"""Phase 6.4 — Agent Payment Protocol conformance and security.

The payment flow is the part of BudgetBuddy where a mistake means
either "the judge paid and got nothing" or "the judge got Pro for
free".  These tests pin down both directions:

  * the protocol exchange is well formed (RequestPayment → Commit →
    Complete, and RequestPayment → Reject)
  * a commit is VERIFIED, not rubber-stamped: a forged signature, a
    wrong amount, a wrong reference and a replayed commit are all
    rejected, and rejection means CancelPayment — never an unlock

Run:  .venv/bin/python tests/test_payments.py
"""

import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

asyncio.set_event_loop(asyncio.new_event_loop())

from uagents_core.identity import Identity  # noqa: E402
from uagents_core.contrib.protocols.payment import (  # noqa: E402
    CommitPayment, RejectPayment, RequestPayment,
    CompletePayment, CancelPayment, payment_protocol_spec,
)

from core.payments import (  # noqa: E402
    PaymentManager, CommitRail, StripeRail, ChainRail,
    BB_METADATA_KEY, PRO_PRICE, PRO_CURRENCY, sign_commitment,
    verify_commit_signature,
)
from core.models import PaymentRequest  # noqa: E402

PASSED = 0
FAILED = 0

BUYER_SEED = "budgetbuddy test buyer seed v1"
ATTACKER_SEED = "budgetbuddy test attacker seed v1"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


def main() -> int:
    print("=" * 60)
    print("  PHASE 6.4 — AGENT PAYMENT PROTOCOL")
    print("=" * 60)

    buyer = Identity.from_seed(BUYER_SEED, 0)
    attacker = Identity.from_seed(ATTACKER_SEED, 0)
    seller = Identity.from_seed("budgetbuddy test seller seed v1", 0)

    # ── 1. protocol spec conformance ──────────────────────────────────
    print("\n[1] Protocol spec")
    check("spec is AgentPaymentProtocol 0.1.0",
          payment_protocol_spec.name == "AgentPaymentProtocol"
          and payment_protocol_spec.version == "0.1.0",
          f"{payment_protocol_spec.name} {payment_protocol_spec.version}")

    from uagents_core.contrib.protocols.payment import Funds

    inter = payment_protocol_spec.interactions
    check("RequestPayment → CommitPayment",
          CommitPayment in inter[RequestPayment])
    check("RequestPayment → RejectPayment",
          RejectPayment in inter[RequestPayment])
    check("CommitPayment → CompletePayment",
          CompletePayment in inter[CommitPayment])
    check("CommitPayment → CancelPayment",
          CancelPayment in inter[CommitPayment])
    check("seller role handles CommitPayment",
          CommitPayment in payment_protocol_spec.roles["seller"])
    check("seller role handles RejectPayment",
          RejectPayment in payment_protocol_spec.roles["seller"])

    # ── 2. building a RequestPayment ──────────────────────────────────
    print("\n[2] RequestPayment construction")
    pm = PaymentManager()
    req = pm.create_pro_request(session_id="sess-1", buyer=buyer.address)
    req.recipient = seller.address
    rp = pm.build_request_payment(req)

    check("is a RequestPayment", isinstance(rp, RequestPayment))
    check("has one accepted_funds entry", len(rp.accepted_funds) == 1)
    funds = rp.accepted_funds[0]
    check("amount is the Pro price", funds.amount == f"{PRO_PRICE:.2f}",
          funds.amount)
    check("currency is USD", funds.currency == PRO_CURRENCY, funds.currency)
    check("payment_method is a known rail",
          funds.payment_method in ("bb_commit", "stripe", "fet_direct"),
          funds.payment_method)
    check("recipient is the seller", rp.recipient == seller.address)
    check("deadline is positive", rp.deadline_seconds > 0)
    check("reference is set and unique", bool(rp.reference) and rp.reference == req.reference)
    check("description mentions Pro", "Pro" in (rp.description or ""))
    check("metadata carries the challenge",
          bool((rp.metadata or {}).get(BB_METADATA_KEY, {}).get("challenge")))
    check("metadata reference matches the request",
          rp.metadata[BB_METADATA_KEY]["reference"] == req.reference)
    check("metadata carries the rail", rp.metadata[BB_METADATA_KEY]["rail"] == req.rail)

    # ── 3. a genuine commit verifies ──────────────────────────────────
    print("\n[3] Genuine commit → verified")
    signature = sign_commitment(req.challenge, buyer)
    commit = CommitPayment(
        funds=funds,
        recipient=rp.recipient,
        transaction_id="tx-abc-123",
        reference=req.reference,
        description=rp.description,
        metadata={BB_METADATA_KEY: {"reference": req.reference, "signature": signature}},
    )
    result = pm.verify_commit(
        request=req, sender=buyer.address, funds=commit.funds,
        transaction_id=commit.transaction_id, metadata=commit.metadata,
    )
    check("genuine commit verifies", result.ok, result.reason)
    check("verification has a human reason", bool(result.reason))

    pm.mark_paid(req.id, commit.transaction_id)
    check("request is marked paid", pm.is_pro(req.id))
    check("transaction id recorded", pm.get_request(req.id).transaction_id == "tx-abc-123")

    # ── 4. forged / malformed commits are REJECTED ────────────────────
    print("\n[4] Forged commits are rejected (no unlock)")

    def fresh() -> PaymentRequest:
        r = pm.create_pro_request(session_id="sess-x", buyer=buyer.address)
        r.recipient = seller.address
        return r

    # 4a. signature from the wrong key
    r = fresh()
    bad_sig = sign_commitment(r.challenge, attacker)
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=funds,
        transaction_id="tx-forged",
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": bad_sig}},
    )
    check("forged signature rejected", not res.ok, res.reason)

    # 4b. signature over a different challenge
    r = fresh()
    other = sign_commitment("some-other-challenge", buyer)
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=funds,
        transaction_id="tx-replay",
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": other}},
    )
    check("signature over a different challenge rejected", not res.ok, res.reason)

    # 4c. wrong amount
    r = fresh()
    wrong_funds = Funds(amount="0.01", currency=PRO_CURRENCY, payment_method=r.rail)
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=wrong_funds,
        transaction_id="tx-cheap",
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": signature}},
    )
    check("underpayment rejected", not res.ok, res.reason)
    check("underpayment names the amount", "amount" in res.reason.lower(), res.reason)

    # 4d. wrong reference
    r = fresh()
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=funds,
        transaction_id="tx-mismatch",
        metadata={BB_METADATA_KEY: {"reference": "not-this-one", "signature": signature}},
    )
    check("reference mismatch rejected", not res.ok, res.reason)

    # 4e. no signature at all
    r = fresh()
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=funds,
        transaction_id="tx-nosig",
        metadata={BB_METADATA_KEY: {"reference": r.reference}},
    )
    check("missing signature rejected", not res.ok, res.reason)

    # 4f. wrong currency
    r = fresh()
    wrong_cur = Funds(amount=f"{PRO_PRICE:.2f}", currency="EUR", payment_method=r.rail)
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=wrong_cur,
        transaction_id="tx-eur",
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": signature}},
    )
    check("wrong currency rejected", not res.ok, res.reason)

    # 4g. wrong payment method
    r = fresh()
    wrong_method = Funds(amount=f"{PRO_PRICE:.2f}", currency=PRO_CURRENCY,
                         payment_method="stripe")
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=wrong_method,
        transaction_id="tx-rail",
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": signature}},
    )
    check("wrong payment method rejected", not res.ok, res.reason)

    # 4h. no transaction id
    r = fresh()
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=funds,
        transaction_id=None,
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": signature}},
    )
    check("missing transaction id rejected", not res.ok, res.reason)

    # 4i. replay: a commit already used for another request
    r = fresh()
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=funds,
        transaction_id="tx-abc-123",
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": signature}},
    )
    check("replayed signature rejected (different challenge)", not res.ok, res.reason)

    # 4j. an already-paid request cannot be paid twice
    res = pm.verify_commit(
        request=req, sender=buyer.address, funds=funds,
        transaction_id=commit.transaction_id, metadata=commit.metadata,
    )
    check("already-paid request cannot be re-verified", not res.ok, res.reason)

    # 4k. expired request
    from datetime import datetime, timedelta
    r = fresh()
    r.expires_at = datetime.now() - timedelta(seconds=1)
    res = pm.verify_commit(
        request=r, sender=buyer.address, funds=funds,
        transaction_id="tx-expired",
        metadata={BB_METADATA_KEY: {"reference": r.reference, "signature": signature}},
    )
    check("expired request rejected", not res.ok, res.reason)

    # ── 5. signature helper is bound to the address ───────────────────
    print("\n[5] Signature ↔ address binding")
    sig_ok = sign_commitment(req.challenge, buyer)
    check("valid signature verifies for the signer",
          verify_commit_signature(buyer.address, req.challenge, sig_ok))
    check("signature does not verify for another address",
          not verify_commit_signature(attacker.address, req.challenge, sig_ok))
    check("garbage signature does not verify",
          not verify_commit_signature(buyer.address, req.challenge, "not-base64!!"))
    check("empty signature does not verify",
          not verify_commit_signature(buyer.address, req.challenge, ""))

    # ── 6. rails ──────────────────────────────────────────────────────
    print("\n[6] Rails")
    check("default rail falls back to bb_commit without credentials",
          pm.default_rail() == "bb_commit", pm.default_rail())

    os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake"
    os.environ["STRIPE_PUBLISHABLE_KEY"] = "pk_test_fake"
    check("stripe rail is chosen when keys are present",
          pm.default_rail() == "stripe", pm.default_rail())
    os.environ.pop("STRIPE_SECRET_KEY", None)
    os.environ.pop("STRIPE_PUBLISHABLE_KEY", None)

    os.environ["AGENT_WALLET_ADDRESS"] = "erd1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    check("chain rail is chosen when a wallet is configured",
          pm.default_rail() == "fet_direct", pm.default_rail())
    os.environ.pop("AGENT_WALLET_ADDRESS", None)

    chain = ChainRail()
    check("chain rail without a wallet is unavailable", not chain.available())
    check("chain rail metadata is empty without a wallet",
          chain.build_metadata(fresh()) == {})

    # Chain verification must consult the chain — an invented hash
    # must NOT pass.
    os.environ["AGENT_WALLET_ADDRESS"] = "erd1testrecipientaddressfortests00000000000000000000000000"
    chain2 = ChainRail()
    check("chain rail with a wallet is available", chain2.available())
    res = chain2.verify(
        transaction_id="0" * 64, funds=Funds(amount="4.99", currency="USD",
                                             payment_method="fet_direct"),
        request=fresh(), sender=buyer.address, metadata=None,
    )
    check("an unknown on-chain transaction is rejected", not res.ok, res.reason)
    os.environ.pop("AGENT_WALLET_ADDRESS", None)

    # ── 7. state machine ──────────────────────────────────────────────
    print("\n[7] Payment state machine")
    pm2 = PaymentManager()
    r = pm2.create_pro_request(session_id="sess-2", buyer=buyer.address)
    check("new request is pending", r.status == "pending")
    check("cancel works on a pending request", pm2.cancel_request(r.id))
    check("cancelled request is not paid", not pm2.is_pro(r.id))
    check("cannot cancel twice", not pm2.cancel_request(r.id))

    r2 = pm2.create_pro_request(session_id="sess-2", buyer=buyer.address)
    check("mark_paid works", pm2.mark_paid(r2.id, "tx-1"))
    check("cannot mark paid twice", not pm2.mark_paid(r2.id, "tx-2"))
    check("transaction id is not overwritten",
          pm2.get_request(r2.id).transaction_id == "tx-1")

    # A fresh pending request, so the lookups have something live to find.
    r3_live = pm2.create_pro_request(session_id="sess-2", buyer=buyer.address)
    found = pm2.request_for_buyer(buyer.address)
    check("request_for_buyer finds the live request",
          found is not None and found.id == r3_live.id,
          found.id if found else "None")
    found_s = pm2.request_for_session("sess-2")
    check("request_for_session finds the live request",
          found_s is not None and found_s.id == r3_live.id,
          found_s.id if found_s else "None")
    check("unknown buyer has no request",
          pm2.request_for_buyer("agent1qnobody") is None)
    check("a paid request is not returned as live",
          pm2.request_for_session("sess-2").status == "pending")

    # ── 8. serialisation round-trip ──────────────────────────────────
    print("\n[8] PaymentRequest round-trip")
    r3 = pm2.create_pro_request(session_id="sess-3", buyer=buyer.address)
    blob = r3.to_dict()
    back = PaymentRequest.from_dict(blob)
    check("id survives", back.id == r3.id)
    check("session survives", back.session_id == r3.session_id)
    check("buyer survives", back.buyer == r3.buyer)
    check("rail survives", back.rail == r3.rail)
    check("reference survives", back.reference == r3.reference)
    check("challenge survives", back.challenge == r3.challenge)
    check("recipient survives", back.recipient == r3.recipient)
    check("json-serialisable", isinstance(json.dumps(blob), str))

    # ── 9. demo ↔ live agent agreement ────────────────────────────────
    # The live payment demo (tools/payment_demo.py) must talk to the
    # agent the Bureau actually runs.  It cannot import agents.host at
    # runtime (that would instantiate a phantom host agent inside the
    # demo process and uAgents would deliver the buyer's message
    # "locally" to it, silently never reaching the real Bureau), so it
    # pins the address as a constant.  If the host seed ever changes,
    # this test fails loudly instead of the demo quietly 404-ing.
    print("\n[9] demo ↔ live host agent agreement")
    try:
        import re
        import tools.payment_demo as demo_mod

        host_src = pathlib.Path("agents/host.py").read_text(encoding="utf-8")
        seed_match = re.search(r'seed\s*=\s*"([^"]+)"', host_src)
        check("agents/host.py declares a seed", seed_match is not None)
        live_address = Identity.from_seed(seed_match.group(1), 0).address

        check("demo default host address matches the host agent's seed",
              demo_mod.DEFAULT_HOST_ADDRESS == live_address,
              f"demo={demo_mod.DEFAULT_HOST_ADDRESS} host={live_address}")
        check("demo host address is a valid agent address",
              demo_mod.DEFAULT_HOST_ADDRESS.startswith("agent1q"),
              demo_mod.DEFAULT_HOST_ADDRESS)
        check("demo default host is not the demo buyer's own address",
              demo_mod.DEFAULT_HOST_ADDRESS != demo_mod.DEMO.address,
              demo_mod.DEMO.address)
    except Exception as exc:  # pragma: no cover - defensive
        check("demo module imports cleanly", False, repr(exc))

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
