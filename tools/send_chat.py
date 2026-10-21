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
from uagents import Agent, Context


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

    # The sender must itself be reachable, or Agentverse cannot route the
    # reply back. Use a mailbox-enabled Agent (registered on Agentverse)
    # rather than a bare Identity.
    from uagents import Agent, Context

    probe = Agent(
        name="budgetbuddy-chat-probe",
        seed="budgetbuddy chat probe sender v1",
        mailbox=True,
        agentverse=True,
        log_level="CRITICAL",
    )

    got: list[str] = []

    @probe.on_message(ChatMessage)
    async def _on_reply(ctx: Context, sender: str, msg: ChatMessage) -> None:
        for item in msg.content:
            if isinstance(item, TextContent) and item.text.strip():
                got.append(item.text)
        await ctx.stop()

    sent = False

    @probe.on_interval(period=2.0)
    async def _send(ctx: Context) -> None:
        nonlocal sent
        if sent:
            return
        sent = True
        print(f"→ query  {text[:60]!r}")
        await ctx.send(
            dest,
            ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid.uuid4(),
                content=[TextContent(type="text", text=text)],
            ),
        )

    async def _timeout() -> None:
        await asyncio.sleep(timeout)
        await probe.stop()

    asyncio.create_task(_timeout())
    await probe.run_async()

    print()
    if got:
        print("=" * 60)
        print("  REPLY FROM BUDGETBUDDY")
        print("=" * 60)
        print(got[0])
        print("=" * 60)
        print("✅ chat protocol round-trip works")
        return 0

    print("❌ no reply captured within the timeout")
    print("   The Bureau log tells the story — look for:")
    print("     '[chat] ← asi1  …'   message arrived")
    print("     '[chat] → asi1  …'   reply sent")
    print("   If both appear, the transport works; the reply just needs a")
    print("   resolvable sender (ASI:One has one — a bare probe may not).")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
