#!/usr/bin/env python3
"""Phase 6 — live card wiring through the real chat handler.

tests/test_cards.py proves the *builders* match the ASI:One schema.
This file proves the *wiring*: drive the actual `_handle_chat` handler
with a ChatMessage the way ASI:One does, and inspect the ChatMessage the
agent sends back for a well-formed MetadataContent block.

That distinction matters because the builders were previously correct-
looking but never called from the chat path at all — every "card" was
dead code.  These tests fail if that ever happens again.

Run:  .venv/bin/python tests/test_cards_live.py
"""

import asyncio
import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

asyncio.set_event_loop(asyncio.new_event_loop())

os.environ["ENABLE_CARDS"] = "true"

from uagents_core.contrib.protocols.chat import (  # noqa: E402
    ChatMessage, TextContent, MetadataContent,
)

import agents.host as host  # noqa: E402
from agents.bus import init_bus  # noqa: E402
from core.cards import VALID_KINDS  # noqa: E402

# Empty address table → every bus.call() takes the in-process fallback,
# which runs the real core modules.  That is the same path a user hits
# when a sub-agent is down, so this test also re-proves the fallback.
init_bus({}, timeout=1)

PASSED = 0
FAILED = 0
SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "samples" / "sample_bank.csv"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


# ── minimal fakes for the uAgents plumbing ────────────────────────────

class FakeLogger:
    def __init__(self):
        self.lines = []

    def _log(self, level, msg):
        self.lines.append(f"{level}: {msg}")

    def info(self, msg): self._log("INFO", msg)
    def warning(self, msg): self._log("WARNING", msg)
    def debug(self, msg): self._log("DEBUG", msg)
    def error(self, msg): self._log("ERROR", msg)

    def find(self, needle):
        return [ln for ln in self.lines if needle in ln]


class FakeCtx:
    """Captures ctx.send() so we can read the outgoing ChatMessage."""

    def __init__(self):
        self.logger = FakeLogger()
        self.sent = []

    async def send(self, sender, msg, *a, **kw):
        self.sent.append((sender, msg))

    def last_chat(self):
        for _sender, msg in reversed(self.sent):
            if isinstance(msg, ChatMessage):
                return msg
        return None


def make_incoming(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


# The session store persists to disk, so a fixed user id would make run N
# depend on run N-1 (a real cold start would never happen).  Mint a fresh
# identity per run: the test then always exercises the same path a new
# ASI:One user takes.
RUN_TAG = uuid4().hex[:12]
USER = f"agent1qcards{RUN_TAG}".ljust(64, "0")[:64]
USER_OFF = f"agent1qoff{RUN_TAG}".ljust(64, "0")[:64]


async def drive(ctx, user_id, text):
    """Run the real handler and return the reply ChatMessage."""
    await host._handle_chat(ctx, user_id, make_incoming(text))
    return ctx.last_chat()


def card_block(msg):
    for item in msg.content:
        if isinstance(item, MetadataContent):
            return item
    return None


def text_of(msg):
    return "\n".join(c.text for c in msg.content if isinstance(c, TextContent))


async def main() -> int:
    print("=" * 60)
    print("  PHASE 6 — LIVE CARD WIRING (real chat handler)")
    print("=" * 60)

    check("cards enabled in host", host.cards.enabled is True)

    ctx = FakeCtx()
    user = USER
    sid = f"asi1-{user}"

    # ── 0. no data yet → no card, but a real answer ───────────────────
    print("\n[0] Cold start (no transactions stored)")
    msg = await drive(ctx, user, "How am I doing?")
    check("agent replied", msg is not None)
    check("cold start sends no card (nothing to render)",
          card_block(msg) is None)

    # ── 1. ingest sample data via the chat path ───────────────────────
    print("\n[1] Ingest via chat")
    csv_text = SAMPLE.read_text()
    msg = await drive(ctx, user, csv_text)
    check("ingest reply mentions parsed rows",
          "Parsed" in text_of(msg), text_of(msg)[:80])
    check("ingest sends no card", card_block(msg) is None)

    # ── 2. analysis → custom dashboard, terminal ──────────────────────
    print("\n[2] 'How am I doing?' → dashboard card")
    msg = await drive(ctx, user, "How am I doing?")
    blk = card_block(msg)
    check("dashboard card attached", blk is not None)
    if blk:
        m = blk.metadata
        check("kind is custom", m.get("card_kind") == "custom")
        check("protocol version 1", m.get("card_protocol_version") == "1")
        check("terminal (informational only)", m.get("is_terminal") == "true")
        check("requires_card_interaction false when terminal",
              m.get("requires_card_interaction") == "false")
        payload = json.loads(m["card_payload"])
        check("payload rooted at 'root'", "root" in payload)
        check("all values are strings",
              all(isinstance(v, str) for v in m.values()))
    check("markdown narration still present alongside the card",
          "Financial Health" in text_of(msg))

    # ── 3. subscriptions → carousel, non-terminal ─────────────────────
    print("\n[3] 'What subscriptions do I have?' → carousel card")
    msg = await drive(ctx, user, "What subscriptions do I have?")
    blk = card_block(msg)
    check("subscriptions card attached", blk is not None)
    if blk:
        m = blk.metadata
        check("kind is carousel", m.get("card_kind") == "carousel")
        check("non-terminal (user can act)",
              m.get("requires_card_interaction") == "true")
        payload = json.loads(m["card_payload"])
        check("carousel has items", len(payload.get("items", [])) > 0)
        titles = " ".join(i["title"].lower() for i in payload["items"])
        check("carousel excludes rent", "rent" not in titles, titles)
        check("carousel includes Netflix", "netflix" in titles, titles)
    check("markdown still lists subscriptions",
          "Recurring Subscriptions" in text_of(msg))

    # ── 4. goal → custom card carrying the plan ───────────────────────
    print("\n[3b] 'Give me tips' → insights carousel")
    msg = await drive(ctx, user, "Can you give me some tips to improve?")
    blk = card_block(msg)
    check("insights card attached", blk is not None)
    if blk:
        m = blk.metadata
        check("kind is carousel", m.get("card_kind") == "carousel")
        payload = json.loads(m["card_payload"])
        check("carousel has insight items", len(payload.get("items", [])) > 0)
        check("items carry a dismiss CTA",
              all("selection" in i.get("primary_cta", {}) for i in payload["items"]))
    check("tips question still routes to analysis text",
          "Financial Health" in text_of(msg))

    print("\n[4] Goal → goal card")
    msg = await drive(ctx, user, "I want to save $3000 by Dec 2027")
    blk = card_block(msg)
    check("goal card attached", blk is not None)
    if blk:
        m = blk.metadata
        check("kind is custom", m.get("card_kind") == "custom")
        payload = json.loads(m["card_payload"])
        flat = json.dumps(payload)
        check("card carries the target amount", "3,000" in flat or "3000" in flat, flat[:200])
        check("card shows a deadline", "2027" in flat, flat[:200])

    # ── 4b. split → custom card carrying the shares ───────────────────
    print("\n[4b] Split → split card")
    msg = await drive(ctx, user, "Split this $90 dinner with Alice and Bob")
    blk = card_block(msg)
    check("split card attached", blk is not None)
    if blk:
        m = blk.metadata
        check("kind is custom", m.get("card_kind") == "custom")
        payload = json.loads(m["card_payload"])
        flat = json.dumps(payload)
        check("card carries the total", "90" in flat, flat[:200])
        check("card lists every share",
              all(n in flat for n in ("You", "Alice", "Bob")), flat[:300])
        check("card offers a settle action",
              "settle_share" in flat, flat[:300])
    check("markdown still shows the split",
          "90" in text_of(msg), text_of(msg)[:120])

    # ── 5. payment → review card with both CTAs ───────────────────────
    print("\n[5] Payment → review (checkout) card")
    msg = await drive(ctx, user, "How do I unlock Pro?")
    blk = card_block(msg)
    check("checkout card attached", blk is not None)
    if blk:
        m = blk.metadata
        check("kind is review", m.get("card_kind") == "review")
        payload = json.loads(m["card_payload"])
        check("has summary_rows", len(payload.get("summary_rows", [])) > 0)
        check("has approve_cta", "approve_cta" in payload)
        check("has reject_cta", "reject_cta" in payload)
        check("approve carries a request id",
              "request_id" in payload["approve_cta"]["selection"])
        check("approve action is confirm_payment",
              payload["approve_cta"]["selection"]["action"] == "confirm_payment")

    # ── 6. every emitted card is schema-valid ─────────────────────────
    print("\n[6] Every card emitted on this session is valid")
    emitted = 0
    for _sender, m in ctx.sent:
        if not isinstance(m, ChatMessage):
            continue
        blk = card_block(m)
        if not blk:
            continue
        emitted += 1
        md = blk.metadata
        ok = (
            md.get("card_protocol_version") == "1"
            and md.get("card_kind") in VALID_KINDS
            and md.get("requires_card_interaction") in ("true", "false")
            and isinstance(md.get("card_payload"), str)
            and len(md["card_payload"].encode()) <= 64 * 1024
            and isinstance(json.loads(md["card_payload"]), dict)
            and all(isinstance(v, str) for v in md.values())
        )
        check(f"card #{emitted} ({md.get('card_kind')}) valid", ok)
    check("at least 4 cards were emitted across the session", emitted >= 4, f"got {emitted}")

    # ── 7. a card click round-trips back as a selection ───────────────
    print("\n[7] Card selection round-trip (click → instruction → reply)")
    confirm = json.dumps({"action": "confirm_payment", "request_id": "req_x"})
    before = len(ctx.sent)
    msg = await drive(ctx, user, confirm)
    check("selection was recognised",
          any("← selection" in ln for ln in ctx.logger.find("[cards]")),
          "; ".join(ctx.logger.find("[cards]")))
    check("agent answered the selection", msg is not None and len(ctx.sent) > before)
    check("answer is not the raw JSON echoed back",
          "confirm_payment" not in text_of(msg))

    parsed = host._parse_card_selection('{"action": "review_subscription", "merchant": "Netflix"}')
    check("_parse_card_selection reads JSON", isinstance(parsed, dict) and parsed["merchant"] == "Netflix")
    check("_parse_card_selection ignores prose",
          host._parse_card_selection("I picked the first offer") is None)
    check("_parse_card_selection ignores malformed JSON",
          host._parse_card_selection("{not json") is None)

    # ── 8. cards OFF → text still tells the whole story ───────────────
    print("\n[8] ENABLE_CARDS=false → identical text, zero cards")
    host.cards.enabled = False
    try:
        ctx2 = FakeCtx()
        user2 = USER_OFF
        await drive(ctx2, user2, SAMPLE.read_text())
        m2 = await drive(ctx2, user2, "How am I doing?")
        check("no card when disabled", card_block(m2) is None)
        check("text still reports financial health", "Financial Health" in text_of(m2))
        m3 = await drive(ctx2, user2, "What subscriptions do I have?")
        check("subscriptions text intact", "Recurring Subscriptions" in text_of(m3))
    finally:
        host.cards.enabled = True

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.get_event_loop().run_until_complete(main()))
