#!/usr/bin/env python3
"""Phase 5 — Agentverse Inspector endpoint tests.

The Agentverse Local Agent Inspector queries GET /agent_info on the
Bureau to discover the agent and create its mailbox. It sends NO special
headers, so the endpoint must be unambiguous.

Regression guard for a real bug: every uAgent registers its own
/agent_info, /messages, /connect and /disconnect, so with 6 agents in one
Bureau there were 6 handlers per path and the server replied:

    400 {"error": "missing header: x-uagents-address",
         "message": "Multiple handlers found for REST endpoint."}

which is exactly "Could not find this Agent on your local host" in the
Inspector. Sub-agents now run with enable_agent_inspector=False and the
Bureau bridges only the host's endpoints.

These tests inspect the built Bureau in-process (no server needed).

Run:  .venv/bin/python tests/test_inspector.py
"""

import asyncio
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

asyncio.set_event_loop(asyncio.new_event_loop())

from agents.run import build_bureau  # noqa: E402
from agents.host import host_agent  # noqa: E402
from agents.subagents import (  # noqa: E402
    ingest_agent, analyst_agent, coach_agent, goal_agent, splitter_agent,
)

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


def main() -> int:
    print("=" * 60)
    print("  PHASE 5 — AGENTVERSE INSPECTOR ENDPOINTS")
    print("=" * 60)

    bureau = build_bureau()
    counts = Counter((m, e) for (_a, m, e) in bureau._server._rest_handler_map)

    # ── 1. the Inspector's endpoint is unambiguous ────────────────────
    print("\n[1] Inspector endpoints resolve to exactly one handler")
    for path in ("/agent_info", "/messages", "/connect", "/disconnect"):
        n = sum(v for (m, e), v in counts.items() if e == path)
        check(f"{path} → 1 handler", n == 1, f"found {n}")

    # ── 2. host endpoints are reachable ───────────────────────────────
    print("\n[2] Host endpoints present")
    for (m, e) in (("GET", "/agent_info"), ("GET", "/health"), ("POST", "/submit")):
        check(f"{m} {e}", (m, e) in counts and counts[(m, e)] == 1)

    # ── 3. sub-agents keep the inspector off ──────────────────────────
    print("\n[3] Sub-agents have the inspector disabled")
    for name, agent in (
        ("ingest", ingest_agent), ("analyst", analyst_agent),
        ("coach", coach_agent), ("goal", goal_agent), ("splitter", splitter_agent),
    ):
        check(f"{name} inspector off", agent._enable_agent_inspector is False)

    # ── 4. exactly ONE agent has it on ────────────────────────────────
    print("\n[4] Only the host serves the inspector")
    enabled = [
        n for n, a in (
            ("host", host_agent), ("ingest", ingest_agent), ("analyst", analyst_agent),
            ("coach", coach_agent), ("goal", goal_agent), ("splitter", splitter_agent),
        ) if a._enable_agent_inspector
    ]
    check("exactly one agent enables it", enabled == ["host"], f"got {enabled}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
