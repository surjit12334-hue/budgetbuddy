#!/usr/bin/env python3
"""Phase 6.2 — live interactive-card demo.

Drives the **running Bureau** over the **real** transport (a real buyer
agent sending real Chat Protocol messages) and reports, for every
card-producing turn, the card that came back.

This is the on-the-wire proof that the cards are not dead code: the
same builder code the ASI:One chat handler uses, exercised over the
network, with the card arriving as an extra ``MetadataContent`` block
next to the markdown reply.

Usage:
    .venv/bin/python tools/card_demo.py

    CARD_DEMO_SEED=...   use a different buyer identity (fresh session)
    CARD_DEMO_HOST=...   talk to a different seller address
    CARD_DEMO_TEXT=1     also print the full markdown reply of each turn
    CARD_DEMO_OUT=...    write the replies/cards to a JSON file

The host agent's address is pinned the same way ``tools/payment_demo.py``
pins it — importing ``agents.host`` here would create a phantom host
agent inside this process and uAgents would deliver the messages
"locally" to it, so they would never reach the real Bureau.  The
agreement is asserted by ``tests/test_payments.py``.
"""

import asyncio
import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Python 3.14 needs an event loop before uagents imports.
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

from uagents import Agent, Context  # noqa: E402
from uagents_core.contrib.protocols.chat import (  # noqa: E402
    ChatMessage, ChatAcknowledgement, TextContent, MetadataContent,
)

# Keep in sync with agents/host.py — asserted by tests/test_payments.py.
DEFAULT_HOST_ADDRESS = "agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9"

HOST_ADDRESS = os.environ.get("CARD_DEMO_HOST", "").strip() or DEFAULT_HOST_ADDRESS
DEMO_PORT = int(os.environ.get("CARD_DEMO_PORT", "8016"))
DEMO_SEED = os.environ.get("CARD_DEMO_SEED", "budgetbuddy card demo buyer v1")
SHOW_TEXT = os.environ.get("CARD_DEMO_TEXT", "").lower() in ("1", "true", "yes")
# "1" (default) = every card-bearing turn must deliver a card.
# "0" = the cards-off run: no turn may deliver a card, and the markdown
#        must still carry the whole story.
EXPECT_CARDS = os.environ.get("CARD_DEMO_EXPECT_CARDS", "1").lower() != "0"

SAMPLE_CSV = """Date,Description,Amount
01/02/2024,Employer Payroll Deposit,+3500.00
01/03/2024,Rent Payment - Oakwood Apartments,-1200.00
01/03/2024,Netflix Subscription,-15.99
01/04/2024,Spotify Premium,-9.99
01/05/2024,Adobe Creative Cloud,-19.99
01/05/2024,Whole Foods Market,-125.30
01/06/2024,Starbucks Coffee,-5.45
01/07/2024,Shell Gas Station,-42.00
01/10/2024,Electric Company Bill,-85.50
01/15/2024,Freelance Payment - Design Work,+500.00
01/15/2024,Planet Fitness Gym,-49.99
02/01/2024,Employer Payroll Deposit,+3500.00
02/02/2024,Rent Payment - Oakwood Apartments,-1200.00
02/03/2024,Netflix Subscription,-15.99
02/04/2024,Spotify Premium,-9.99
02/05/2024,Adobe Creative Cloud,-19.99
02/12/2024,T-Mobile Phone Bill,-55.00
02/16/2024,Nike Store,-120.00"""

# (label, message, expected card kind) — None means "no card expected"
TURNS = [
    ("ingest", SAMPLE_CSV, None),
    ("dashboard", "How am I doing?", "custom"),
    ("insights", "Any insights or advice for me?", "carousel"),
    ("subscriptions", "What subscriptions do I have?", "carousel"),
    ("goal", "I want to save $3000 by August", "custom"),
    ("split", "Split this $90 dinner with Alice and Bob", "custom"),
    ("checkout", "How do I unlock Pro?", "review"),
]

DEMO = Agent(
    name="bb_card_demo_buyer",
    seed=DEMO_SEED,
    port=DEMO_PORT,
    endpoint=[f"http://127.0.0.1:{DEMO_PORT}/submit"],
)

CTX: dict = {}
READY = asyncio.Event()
INBOX: asyncio.Queue = asyncio.Queue()


@DEMO.on_event("startup")
async def on_startup(ctx: Context) -> None:
    CTX["ctx"] = ctx
    READY.set()


@DEMO.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
    pass


@DEMO.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
    """Capture the seller's reply: the markdown text and any card."""
    text = ""
    card = None
    for item in msg.content:
        if isinstance(item, TextContent):
            text += item.text
        elif isinstance(item, MetadataContent):
            meta = item.metadata or {}
            card = {
                "card_kind": meta.get("card_kind"),
                "card_protocol_version": meta.get("card_protocol_version"),
                "requires_card_interaction": meta.get("requires_card_interaction"),
                "payload_bytes": len(str(meta.get("card_payload", "")).encode("utf-8")),
            }
    await INBOX.put({"text": text, "card": card})


async def ask(label: str, text: str) -> dict:
    """Send one turn and wait for the seller's reply."""
    ctx = CTX["ctx"]
    status = await ctx.send(
        HOST_ADDRESS,
        ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=text)],
        ),
    )
    box = {"text": "", "card": None, "status": str(status)}
    try:
        box.update(await asyncio.wait_for(INBOX.get(), timeout=25))
    except asyncio.TimeoutError:
        box["text"] = "<timed out>"
    return box


async def main() -> int:
    print("=" * 70)
    print("  BUDGETBUDDY — LIVE INTERACTIVE CARD DEMO")
    print("=" * 70)
    print(f"  host agent : {HOST_ADDRESS}")
    print(f"  buyer agent: {DEMO.address}")
    print("=" * 70)

    task = asyncio.create_task(DEMO.run_async())
    # The startup event fires only after the agent has registered with
    # Agentverse, which can take a few seconds on a cold DNS path.
    try:
        await asyncio.wait_for(READY.wait(), timeout=45)
    except asyncio.TimeoutError:
        print("  ❌ the buyer agent never finished starting up")
        sys.stdout.flush()
        os._exit(1)

    replies: dict = {}
    cards: dict = {}
    failures = 0

    for label, text, expected_kind in TURNS:
        box = await ask(label, text)
        replies[label] = box.get("text", "")
        card = box.get("card")
        if card:
            cards[label] = card

        first = replies[label].splitlines()[0] if replies[label].splitlines() else "<no reply>"
        print(f"\n▶ {label}")
        print(f"   reply  : {first[:92]}")
        if SHOW_TEXT:
            for line in replies[label].splitlines()[1:]:
                print(f"           {line[:92]}")

        if expected_kind is None:
            if card:
                print(f"   ⚠️  unexpected card: {card['card_kind']}")
                if not EXPECT_CARDS:
                    failures += 1
            else:
                print("   card   : (none expected) ✓")
        elif not EXPECT_CARDS:
            # cards-off run: the markdown must still carry the answer
            ok = card is None
            print(
                f"   {'✅' if ok else '⚠️ '} card   : "
                f"{'none (as expected)' if ok else f'unexpectedly {card}'}"
            )
            if not ok:
                failures += 1
            first = replies[label].splitlines()[0] if replies[label].splitlines() else ""
            if not replies[label].strip():
                print("   ⚠️  the markdown reply is empty — the answer was lost")
                failures += 1
            elif len(replies[label].strip()) < 40:
                print(f"   ⚠️  the markdown reply looks truncated: {first[:80]}")
                failures += 1
            else:
                print(f"   ✅ markdown still tells the story ({len(replies[label])} chars)")
        elif card is None:
            print(f"   ⚠️  NO CARD (expected {expected_kind})")
            failures += 1
        else:
            ok = card["card_kind"] == expected_kind
            mark = "✅" if ok else "⚠️ "
            print(
                f"   {mark} card   : kind={card['card_kind']} "
                f"v{card['card_protocol_version']} "
                f"interactive={card['requires_card_interaction']} "
                f"{card['payload_bytes']}B"
            )
            if not ok:
                failures += 1

    print("\n" + "=" * 70)
    if failures == 0:
        if EXPECT_CARDS:
            print(f"  ✅ {len(cards)}/{len(TURNS) - 1} card-bearing turns delivered a card")
        else:
            print(f"  ✅ {len(cards)} card(s) with cards OFF — markdown carried every answer")
    else:
        print(f"  ❌ {failures} turn(s) did not match expectations")
    print("=" * 70)

    out = os.environ.get("CARD_DEMO_OUT", "")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"replies": replies, "cards": cards}, fh, indent=2)
        print(f"  replies written to {out}")

    sys.stdout.flush()
    os._exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    sys.exit(asyncio.get_event_loop().run_until_complete(main()))
