#!/usr/bin/env python3
"""Phase 2 fallback test — verify that killing a sub-agent still
produces an answer via the in-process fallback."""

import asyncio
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

from uagents import Context, Model

from agents.bus import AgentBus
from agents.host import _fallback_ingest, _fallback_analysis
from agents.messages import IngestRequest, IngestResponse, AnalysisResponse

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}  {detail}")


# Mock context that mimics uagents Context enough for logging
class MockCtx:
    class logger:
        @staticmethod
        def info(msg): print(f"    {msg}")
        @staticmethod
        def warning(msg): print(f"    {msg}")

    async def send_and_receive(self, *a, **kw):
        raise ConnectionError("agent unreachable (simulated kill)")


async def main():
    print("=" * 60)
    print("PHASE 2 FALLBACK TEST  (sub-agent 'killed')")
    print("=" * 60)

    # ── 2.4a: AgentBus falls back when address is bogus ──
    print("\n[2.4] AgentBus fallback on unreachable agent")
    bus = AgentBus(addresses={"ingest": "agent1qfakefakefakefakefakefakefakefakefake"}, timeout=2)
    ctx = MockCtx()

    resp = await bus.call(
        ctx, "ingest",
        IngestRequest(request_id="t1", session_id="fallback-test", text="spent $5 on coffee"),
        IngestResponse,
        fallback=lambda: _fallback_ingest("fallback-test", "spent $5 on coffee"),
    )
    check("fallback returns IngestResponse", isinstance(resp, IngestResponse))
    check("fallback parsed 1 txn", resp.txn_count == 1, f"got {resp.txn_count}")
    check("fallback reply mentions income/expenses", "Income" in resp.reply or "Expenses" in resp.reply)

    # ── 2.4b: fallback analysis works after fallback ingest ──
    resp2 = await bus.call(
        ctx, "analyst",
        IngestRequest(request_id="t2", session_id="fallback-test", text=""),
        AnalysisResponse,
        fallback=lambda: _fallback_analysis("fallback-test"),
    )
    check("fallback analysis returns AnalysisResponse", isinstance(resp2, AnalysisResponse))
    check("fallback analysis has report", len(resp2.report) > 20, f"got: {resp2.report[:60]}")

    # ── 2.4c: no address registered → still works ──
    bus2 = AgentBus(addresses={}, timeout=2)
    resp3 = await bus2.call(
        ctx, "goal",
        IngestRequest(request_id="t3", session_id="x", text=""),
        IngestResponse,
        fallback=lambda: _fallback_ingest("x", "spent $10 on lunch"),
    )
    check("no address → fallback fires", isinstance(resp3, IngestResponse))

    print()
    print("=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


sys.exit(_loop.run_until_complete(main()))
