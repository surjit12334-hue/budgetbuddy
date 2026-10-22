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
import os
import pathlib
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
from uagents import Agent, Context

#: The probe's identity.  It only has to be stable enough for the
#: Almanac record; the reply comes back over localhost, so a stale
#: mailbox can never break this check.
PROBE_SEED = os.environ.get("SEND_CHAT_PROBE_SEED", "budgetbuddy chat probe sender v2")
PROBE_PORT = int(os.environ.get("SEND_CHAT_PROBE_PORT", "8017"))


def host_address() -> str:
    req = urllib.request.Request(
        "http://localhost:8001/health",
        headers={"User-Agent": "budgetbuddy-send-chat/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["agents"]["host"]


async def main() -> int:
    args = [a for a in sys.argv[1:] if a not in ("--sample",)]
    if not args:
        print('usage: send_chat.py "your message" [timeout_seconds] [--sample]')
        print()
        print("  --sample   paste samples/sample_bank.csv first, exactly like")
        print("             the demo does, so the reply is a real dashboard")
        return 2
    text = args[0]
    timeout = int(args[1]) if len(args) > 1 else 60
    with_sample = "--sample" in sys.argv[1:]

    dest = os.environ.get("SEND_CHAT_TO", "").strip() or host_address()
    print(f"→ to     {dest[:40]}…")

    # The sender must be registered, or Agentverse cannot route the reply
    # back to it.  It is registered with a LOCAL endpoint (127.0.0.1) the
    # same way the card demo's buyer is: a mailbox-enabled probe would
    # need a mailbox that a human creates once in the Inspector, and that
    # mailbox goes stale — the reply then fails with "404: Target agent
    # not found" even though the host answered perfectly.
    #
    # The interesting half of this test — the message travelling IN
    # through the real Agentverse mailbox to the host — is unchanged.
    from uagents import Agent, Context

    probe = Agent(
        name="budgetbuddy-chat-probe",
        seed=PROBE_SEED,
        port=PROBE_PORT,
        endpoint=[f"http://127.0.0.1:{PROBE_PORT}/submit"],
        agentverse=True,
        # ERROR, not CRITICAL: the sender-side delivery failure is the
        # single most useful diagnostic this tool gives ("404: Target
        # agent not found" == the host has no mailbox yet).
        log_level="ERROR",
    )

    got: list[str] = []

    replied = asyncio.Event()

    # The turns to send, in order.  With --sample the demo CSV goes
    # first, so the reply is a real dashboard instead of "paste your
    # spending data first".
    turns: list[str] = []
    if with_sample:
        sample = pathlib.Path(__file__).resolve().parent.parent / "samples" / "sample_bank.csv"
        if sample.exists():
            turns.append(sample.read_text(encoding="utf-8").strip())
            print("→ paste  samples/sample_bank.csv")
    turns.append(text)

    awaiting_reply = False

    @probe.on_message(ChatMessage)
    async def _on_reply(ctx: Context, sender: str, msg: ChatMessage) -> None:
        nonlocal awaiting_reply
        for item in msg.content:
            if isinstance(item, TextContent) and item.text.strip():
                got.append(item.text)
        awaiting_reply = False
        if not turns:
            replied.set()

    @probe.on_interval(period=1.0)
    async def _send(ctx: Context) -> None:
        nonlocal awaiting_reply
        if awaiting_reply or not turns:
            return
        outgoing = turns.pop(0)
        awaiting_reply = True
        print(f"→ query  {outgoing[:60]!r}")
        await ctx.send(
            dest,
            ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid.uuid4(),
                content=[TextContent(type="text", text=outgoing)],
            ),
        )

    def _report() -> int:
        print()
        if got:
            print("=" * 60)
            print("  REPLY FROM BUDGETBUDDY")
            print("=" * 60)
            print(got[-1])
            print("=" * 60)
            print("✅ chat protocol round-trip works")
            return 0

        print("❌ no reply captured within the timeout")
        print("   Look for the error above this line:")
        print("     'Unable to resolve destination endpoint'  the host has")
        print("        no mailbox yet — create one in the Agent Inspector")
        print("     '404: Target agent not found'              same cause")
        print("   Then check the Bureau log for:")
        print("     '[chat] ← asi1  …'   the message arrived")
        print("     '[chat] → asi1  …'   the reply was sent")
        return 1

    async def _expire() -> None:
        await asyncio.sleep(timeout)
        replied.set()

    asyncio.create_task(_expire())
    runner = asyncio.create_task(probe.run_async())

    # Wait for the reply (or the timeout) on our own event.  `run_async()`
    # does not return when the agent stops, so waiting for it would hang
    # this script and the result would never be printed.
    await replied.wait()

    code = _report()

    # uagents 0.26 has no Agent.stop(); cancelling the runner cancels the
    # agent's server and mailbox tasks.  But its shutdown path swallows
    # the cancellation and waits on a socket that may never close, so
    # awaiting the task would hang this script.  A probe has nothing to
    # flush, so leave hard.
    runner.cancel()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    asyncio.run(main())
