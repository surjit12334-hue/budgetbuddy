#!/usr/bin/env python3
"""Send a real Chat Protocol message to BudgetBuddy via Agentverse.

Exercises the EXACT path ASI:One uses: a ChatMessage addressed to the
agent and delivered through the Agentverse mailbox. Use it to prove the
chat interface works before (or without) clicking around the UI.

Usage:
    .venv/bin/python tools/send_chat.py "Help"

Exit code 0 if a reply came back, 1 otherwise.
"""

import asyncio
import json
import pathlib
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
from uagents_core.identity import Identity
from uagents.communication import send_message


def host_address() -> str:
    req = urllib.request.Request(
        "http://localhost:8001/health",
        headers={"User-Agent": "budgetbuddy-send-chat/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["agents"]["host"]


async def main() -> int:
    if len(sys.argv) < 2:
        print('usage: send_chat.py "your message" [timeout_seconds]')
        return 2
    text = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    dest = host_address()
    print(f"→ to     {dest[:40]}…")

    # A throwaway identity carries the round-trip.
    sender = Identity.from_seed("budgetbuddy chat probe sender v1", 0)

    msg = ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid.uuid4(),
        content=[TextContent(type="text", text=text)],
    )

    print(f"→ query  {text[:60]!r}")
    reply = await send_message(
        destination=dest,
        message=msg,
        response_type=ChatMessage,
        sender=sender,
        timeout=timeout,
    )

    print()
    if isinstance(reply, ChatMessage):
        out = "\n".join(
            i.text for i in reply.content if isinstance(i, TextContent) and i.text.strip()
        )
        if out:
            print("=" * 60)
            print("  REPLY FROM BUDGETBUDDY")
            print("=" * 60)
            print(out)
            print("=" * 60)
            print("✅ chat protocol round-trip works")
            return 0

    # A FAILED MsgStatus means Agentverse couldn't hand it to the agent.
    # In practice that is the missing mailbox (404: Target agent not found).
    status = str(getattr(reply, "status", "")).lower()
    detail = getattr(reply, "detail", "") or ""
    if "failed" in status or "Target agent not found" in detail or "404" in detail:
        print("❌ Agentverse was reached, but could not deliver the message.")
        print()
        print("   Almost always this means the MAILBOX does not exist yet.")
        print("   Look for this line just above:")
        print("     '404: Target agent not found'  → mailbox missing")
        print()
        print("   In Agentverse:")
        print("     1. Open the agent's page → Agent Inspector / Mailbox")
        print("     2. Click 'Create Mailbox'")
        print("   Then re-run this command — no restart of the Bureau needed.")
        return 1

    print(f"❌ no usable reply (got {type(reply).__name__}: {detail[:100]!r})")
    print("   → is the Bureau running? (./keepalive.sh)")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
