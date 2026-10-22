#!/usr/bin/env python3
"""Phase 6.4 — end-to-end payment demo.

Runs the real thing:

    1. the Bureau (host agent) is already running on :8001
    2. a buyer agent starts and says "unlock Pro" to the host
    3. the host replies with a RequestPayment (Agent Payment Protocol)
    4. the buyer signs the challenge and replies with a CommitPayment
    5. the host verifies the signature and replies with CompletePayment
    6. the host's chat message confirms Pro is unlocked

Nothing is stubbed: these are real uAgents talking over the network.

Usage:
    .venv/bin/python tools/payment_demo.py

The host address defaults to the BudgetBuddy host agent; override with
HOST_ADDRESS=agent1q...
"""

import asyncio
import os
import pathlib
import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Python 3.14 needs an event loop before uagents imports.
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

from uagents import Agent, Context, Protocol  # noqa: E402
from uagents_core.contrib.protocols.chat import (  # noqa: E402
    ChatMessage, TextContent,
)
from uagents_core.contrib.protocols.payment import (  # noqa: E402
    CommitPayment, RejectPayment, RequestPayment,
    CompletePayment, CancelPayment, payment_protocol_spec,
)
from uagents_core.identity import Identity  # noqa: E402

from core.payments import BB_METADATA_KEY, sign_commitment  # noqa: E402
from agents.identity import known_address, live_bureau_address  # noqa: E402

# The last-resort address — the one the demo agent uses when nothing
# else is known.  It matches the seed the live Bureau ships with.
DEFAULT_HOST_ADDRESS = "agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9"


def _resolve_host_address() -> str:
    """Find the seller.

    The host agent's address lives in ``agents/host.py``.  We must NOT
    import that module here: importing it instantiates a *second* host
    agent inside the demo process, and uAgents then delivers the
    buyer's message "locally" to that phantom agent (whose message
    queue is never serviced) instead of sending it to the real Bureau.

    So ask, in order:
      1. ``HOST_ADDRESS`` — an explicit override
      2. the running Bureau's own health endpoint — the only answer that
         cannot be wrong, because it is served by the process that is
         actually answering ASI:One
      3. the address derived from the seed we resolve
      4. the last-resort constant above
    """
    env = os.environ.get("HOST_ADDRESS", "").strip()
    if env:
        return env
    live = live_bureau_address("host")
    if live:
        return live
    return known_address("host") or DEFAULT_HOST_ADDRESS


HOST_ADDRESS = _resolve_host_address()
DEMO_PORT = int(os.environ.get("DEMO_BUYER_PORT", "8015"))

# ── modes ──────────────────────────────────────────────────────────────
# The demo buyer can behave three ways.  Each mode uses a DISTINCT
# buyer identity, so every mode gets its own session and the outcomes
# are independently provable in the session store.
#
#   (default)      commit honestly      → CompletePayment, Pro unlocked
#   DEMO_FORGE=1   forge the signature  → CancelPayment, no Pro
#   DEMO_REJECT=1  decline the invoice  → no Pro
FORGE = os.environ.get("DEMO_FORGE", "").lower() in ("1", "true", "yes")
REJECT = os.environ.get("DEMO_REJECT", "").lower() in ("1", "true", "yes")
FORGER_SEED = os.environ.get("DEMO_FORGER_SEED", "budgetbuddy payment demo forger v1")
forger_identity = Identity.from_seed(FORGER_SEED, 0)

# A distinct seed per mode ⇒ a distinct agent address ⇒ a distinct
# session id (asi1-<address>), so "no Pro" is provable per run.
MODE_SUFFIX = "-forge" if FORGE else ("-reject" if REJECT else "")
DEMO_SEED = os.environ.get(
    "DEMO_BUYER_SEED", "budgetbuddy payment demo buyer v1" + MODE_SUFFIX
)

DEMO = Agent(
    name="bb_payment_demo_buyer",
    seed=DEMO_SEED,
    port=DEMO_PORT,
    endpoint=[f"http://127.0.0.1:{DEMO_PORT}/submit"],
)
demo_identity = Identity.from_seed(DEMO_SEED, 0)
payment_proto = Protocol(spec=payment_protocol_spec, role="buyer")

STATE = {
    "request": None,
    "committed": False,
    "completed": False,
    "cancelled": False,
    "rejected": False,
    "pro_unlocked": False,
    "reply": "",
}


@payment_proto.on_message(RequestPayment)
async def on_request(ctx: Context, sender: str, msg: RequestPayment) -> None:
    print("\n[2] ← RequestPayment received")
    print(f"      from     : {sender}")
    print(f"      funds    : {msg.accepted_funds}")
    print(f"      reference: {msg.reference}")
    print(f"      deadline : {msg.deadline_seconds}s")

    bb = (msg.metadata or {}).get(BB_METADATA_KEY) or {}
    challenge = bb.get("challenge", "")

    # ── decline ──
    if REJECT:
        print("      ⚠️  REJECT MODE: declining the invoice")
        STATE["rejected"] = True
        await ctx.send(sender, RejectPayment(reason="demo buyer declined"))
        print("      → RejectPayment sent")
        return

    print(f"      challenge: {challenge[:24]}…")

    signing_identity = forger_identity if FORGE else demo_identity
    signature = sign_commitment(challenge, signing_identity) if challenge else ""
    if FORGE:
        print("      ⚠️  FORGED MODE: signed with a key that is NOT this address")
    else:
        print("      signed the challenge with the buyer identity")

    STATE["request"] = msg
    commit = CommitPayment(
        funds=msg.accepted_funds[0],
        recipient=msg.recipient,
        transaction_id=f"bb-demo-{uuid4().hex[:12]}",
        reference=msg.reference,
        description=msg.description,
        metadata={
            BB_METADATA_KEY: {
                "reference": msg.reference or bb.get("reference", ""),
                "signature": signature,
            }
        },
    )
    STATE["committed"] = True
    await ctx.send(sender, commit)
    print(f"      → CommitPayment sent ({commit.transaction_id})")


@payment_proto.on_message(CompletePayment)
async def on_complete(ctx: Context, sender: str, msg: CompletePayment) -> None:
    print("\n[4] ✓ CompletePayment received — the seller verified the payment")
    STATE["completed"] = True


@payment_proto.on_message(CancelPayment)
async def on_cancel(ctx: Context, sender: str, msg: CancelPayment) -> None:
    print(f"\n[4] ✗ CancelPayment received: {msg.reason}")
    STATE["cancelled"] = True


@DEMO.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
    """The seller's chat reply (the Pro confirmation)."""
    for item in msg.content:
        text = getattr(item, "text", None)
        if text:
            STATE["reply"] = text
            first = text.splitlines()[0] if text.splitlines() else text
            print(f"\n[3] ← chat from seller: {first}")
            if "Pro unlocked" in text or "Payment confirmed" in text:
                STATE["pro_unlocked"] = True


@DEMO.on_event("startup")
async def on_startup(ctx: Context) -> None:
    print(f"[1] demo buyer address: {ctx.agent.address}")
    print(f"    sending 'unlock Pro' to {HOST_ADDRESS}")
    status = await ctx.send(
        HOST_ADDRESS,
        ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text="How do I unlock Pro?")],
        ),
    )
    # ctx.send() returns a MsgStatus on failure — never ignore it, or a
    # broken send looks exactly like a silent server.
    print(f"    send status: {status}")


async def watch_for_unlock() -> None:
    """Wait for the seller's CompletePayment (or a CancelPayment)."""
    for _ in range(60):
        await asyncio.sleep(0.5)
        if STATE["completed"] or STATE["cancelled"] or STATE["rejected"]:
            break
    print(f"\n[5] completed={STATE['completed']} cancelled={STATE['cancelled']} "
          f"rejected={STATE['rejected']}")


async def main() -> int:
    print("=" * 64)
    print("  BUDGETBUDDY — AGENT PAYMENT PROTOCOL END-TO-END DEMO")
    print("=" * 64)
    print(f"  host agent: {HOST_ADDRESS}")
    print(f"  rails     : bb_commit (signed proof of commitment)")
    print("=" * 64)

    if not HOST_ADDRESS:
        print("  ❌ no host address — set HOST_ADDRESS=agent1q...")
        return 1

    DEMO.include(payment_proto, publish_manifest=True)

    # Agent.run() would call run_until_complete on the loop we are
    # already running in, so drive run_async() as a task instead.
    task = asyncio.create_task(DEMO.run_async())
    await watch_for_unlock()

    print("\n" + "=" * 64)
    if FORGE:
        # The expected outcome of a forged commit is a REFUSAL.
        if STATE["cancelled"] and not STATE["completed"]:
            print("  ✅ FORGED COMMIT REJECTED — no Pro unlocked (correct)")
        else:
            print("  ❌ forged commit was NOT rejected — this is a security bug")
        code = 0 if (STATE["cancelled"] and not STATE["completed"]) else 1
    elif REJECT:
        if STATE["rejected"] and not STATE["completed"]:
            print("  ✅ INVOICE DECLINED — no Pro unlocked (correct)")
        else:
            print("  ❌ decline was not handled correctly")
        code = 0 if (STATE["rejected"] and not STATE["completed"]) else 1
    elif STATE["completed"]:
        print("  ✅ PAYMENT COMPLETED IN-CHAT — Pro unlocked")
        code = 0
    elif STATE["cancelled"]:
        print("  ❌ payment was cancelled by the seller")
        code = 1
    else:
        port = os.environ.get("HOST_PORT", "8001")
        print(f"  ⚠️  no payment round-trip (is the Bureau running on :{port}?)")
        code = 1
    print("=" * 64)

    # uAgents' agent task tree is deep; cancelling it recursively blows
    # the stack and buries the result in asyncio noise.  The demo's
    # value is the result, so report it and leave.
    sys.stdout.flush()
    os._exit(code)


if __name__ == "__main__":
    sys.exit(asyncio.get_event_loop().run_until_complete(main()))
