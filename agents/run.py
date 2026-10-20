"""Bureau entrypoint — start all 6 agents with one command.

    python -m agents.run

Creates the event loop (Python 3.14 requirement), instantiates every
agent, wires the AgentBus, registers the host REST endpoint with the
Bureau server, and runs forever.
"""

import asyncio
import sys
import os

# ── ensure event loop exists before uagents imports ────────────────────
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

from uagents import Bureau

from .host import host_agent
from .subagents import (
    ingest_agent, analyst_agent, coach_agent, goal_agent, splitter_agent,
)
from .bus import init_bus

AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "15"))
BUREAU_PORT = int(os.environ.get("HOST_PORT", "8001"))


def _copy_rest_endpoints(bureau: Bureau, agent) -> None:
    """Copy an agent's REST endpoint registrations into the Bureau's server.

    uAgents' Bureau uses its own ASGIServer; agents register REST
    endpoints on their own (never-started) server.  This bridge copies
    the registrations so the Bureau can route external requests.
    """
    for (address, method, endpoint), details in agent._server._rest_handler_map.items():
        bureau._server.add_rest_endpoint(
            address, method, endpoint,
            details.request_model, details.response_model,
        )


def build_bureau() -> Bureau:
    agents = [
        host_agent,
        ingest_agent,
        analyst_agent,
        coach_agent,
        goal_agent,
        splitter_agent,
    ]

    # Wire the AgentBus with sub-agent addresses
    init_bus(
        {
            "ingest":   ingest_agent.address,
            "analyst":  analyst_agent.address,
            "coach":    coach_agent.address,
            "goal":     goal_agent.address,
            "splitter": splitter_agent.address,
        },
        timeout=AGENT_TIMEOUT,
    )

    bureau = Bureau(agents=agents, port=BUREAU_PORT)

    # Bridge the host agent's REST endpoint into the Bureau server
    _copy_rest_endpoints(bureau, host_agent)

    return bureau


def main() -> None:
    bureau = build_bureau()

    print("=" * 60)
    print("  BudgetBuddy — multi-agent ACP system")
    print("=" * 60)
    print(f"  Host agent address:  {host_agent.address}")
    print(f"  Ingest agent:        {ingest_agent.address}")
    print(f"  Analyst agent:       {analyst_agent.address}")
    print(f"  Coach agent:         {coach_agent.address}")
    print(f"  Goal agent:          {goal_agent.address}")
    print(f"  Splitter agent:      {splitter_agent.address}")
    print()
    print(f"  REST endpoint:  POST http://localhost:{BUREAU_PORT}/submit")
    print(f"  Agent timeout:  {AGENT_TIMEOUT}s")
    print("=" * 60)
    sys.stdout.flush()

    bureau.run()


if __name__ == "__main__":
    main()
