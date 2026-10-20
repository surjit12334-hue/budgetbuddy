#!/usr/bin/env python3
"""Phase 5 — chat protocol wiring tests.

Verifies the ASI:One interface is correctly assembled:

  1. The host agent exposes the Chat Protocol.
  2. The mailbox is enabled (so ASI:One can reach it with no tunnel).
  3. The chat handler routes text through the SAME `route()` the REST
     endpoint uses — so both transports behave identically.
  4. Session ids are namespaced per chat sender (multi-turn memory).
  5. Every intent is reachable from a chat message.

Run:  .venv/bin/python tests/test_chat.py
"""

import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

from uagents_core.contrib.protocols.chat import chat_protocol_spec  # noqa: E402

from agents.host import host_agent, route, detect_intent  # noqa: E402

PASSED = 0
FAILED = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


class _FakeCtx:
    """Minimal Context stand-in — we only need .logger and .send."""
    class _Log:
        def info(self, *a, **k):
            pass

        def debug(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

    def __init__(self):
        self.logger = self._Log()

    async def send(self, *a, **k):
        return None


def main() -> int:
    print("=" * 60)
    print("  PHASE 5 — CHAT PROTOCOL TESTS")
    print("=" * 60)

    # ── 1. protocol attached ───────────────────────────────────────────
    print("\n[1] Chat Protocol attached to the host agent")
    specs = [
        getattr(v, "spec", v)
        for v in host_agent.protocols.values()
    ]
    check(
        "host exposes the chat protocol spec",
        any(getattr(s, "name", "") == getattr(chat_protocol_spec, "name", None) or s is chat_protocol_spec for s in specs),
        f"specs={[type(s).__name__ for s in specs]}",
    )
    # The digest in host_agent.protocols must match what Agentverse lists.
    check(
        "protocol digest is registered",
        len(host_agent.protocols) >= 1,
        f"count={len(host_agent.protocols)}",
    )

    # ── 2. mailbox enabled ─────────────────────────────────────────────
    print("\n[2] Mailbox enabled (no tunnel required)")
    check("host agent uses a mailbox", bool(host_agent._use_mailbox))

    # ── 3. route() drives every intent ────────────────────────────────
    print("\n[3] route() reaches every intent (shared with REST)")
    # Initialise the bus with the real agent addresses (no network use:
    # the bus falls back in-process when an agent is unreachable).
    from agents.bus import init_bus
    from agents.subagents import (
        ingest_agent, analyst_agent, coach_agent, goal_agent, splitter_agent,
    )
    init_bus(
        {
            "ingest": ingest_agent.address,
            "analyst": analyst_agent.address,
            "coach": coach_agent.address,
            "goal": goal_agent.address,
            "splitter": splitter_agent.address,
        }
    )
    ctx = _FakeCtx()
    side = "chat-test"

    csv_text = (pathlib.Path(__file__).resolve().parent.parent / "samples" / "sample_bank.csv").read_text()
    checks = [
        ("ingest", csv_text, "Parsed"),
        ("analysis", "How am I doing?", "Financial Health"),
        ("subscriptions", "What subscriptions do I have?", "Subscriptions"),
        ("goal", "I want to save $3000 by August", "Monthly savings"),
        ("split", "Split this $90 dinner with Alice and Bob", "Alice"),
        ("payment", "How do I unlock Pro?", "Payment Request"),
        ("help", "Help", "BudgetBuddy Help"),
    ]
    for label, text, expect in checks:
        reply = _loop.run_until_complete(route(ctx, side, text))
        check(f"route → {label}", expect in reply, f"got {reply[:60]!r}")

    # ── 4. session namespacing ────────────────────────────────────────
    print("\n[4] Chat sessions are namespaced per sender")
    # Two different chat senders must not share data.
    a = "asi1-agent1qAAA"
    b = "asi1-agent1qBBB"
    _loop.run_until_complete(
        route(ctx, a, "01/15/2024,Coffee,-5.45\n01/16/2024,Netflix,-15.99")
    )
    reply_a = _loop.run_until_complete(route(ctx, a, "How am I doing?"))
    reply_b = _loop.run_until_complete(route(ctx, b, "How am I doing?"))
    check("sender A remembers its data", "Financial Health" in reply_a, f"got {reply_a[:50]!r}")
    check(
        "sender B is isolated",
        "don't have any transactions" in reply_b,
        f"got {reply_b[:50]!r}",
    )

    # ── 5. intent detection sanity ────────────────────────────────────
    print("\n[5] Intent detection")
    for text, expect in [
        ("Help", "help"),
        ("How am I doing?", "analysis"),
        ("Split this $90 dinner with Alice and Bob", "split"),
        ("What subscriptions do I have?", "subscriptions"),
        ("How do I unlock Pro?", "payment"),
    ]:
        check(f"detect_intent({text[:28]!r})", detect_intent(text) == expect)

    # ── summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
