"""AgentBus: host → sub-agent calls with timeout + in-process fallback.

If a sub-agent is unreachable or times out, the bus calls the core
module directly so the user still gets an answer.
"""

import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from uagents import Context, Model


class AgentBus:
    def __init__(self, addresses: Dict[str, str], timeout: int = 15):
        self.addresses = addresses
        self.timeout = timeout

    async def call(
        self,
        ctx: Context,
        name: str,
        request: Model,
        response_type: type[Model],
        fallback: Callable[[], Awaitable[Any]],
    ) -> Optional[Model]:
        """Send *request* to the sub-agent *name*.

        Returns the sub-agent's response, or the result of *fallback()*
        if the agent is unreachable / times out.
        """
        addr = self.addresses.get(name)
        if addr:
            ctx.logger.info(f"[bus] → {name:<10}  {type(request).__name__}")
            try:
                resp, status = await ctx.send_and_receive(
                    addr, request, response_type,
                    sync=True, timeout=self.timeout,
                )
                if resp is not None:
                    ctx.logger.info(f"[bus] ← {name:<10}  {type(resp).__name__}")
                    return resp
                ctx.logger.warning(f"[bus] {name} returned no response (status={status})")
            except Exception as exc:
                ctx.logger.warning(f"[bus] {name} unreachable: {exc}")
        else:
            ctx.logger.warning(f"[bus] no address registered for '{name}'")

        # ── in-process fallback ──
        ctx.logger.info(f"[bus] ↻ fallback → {name}")
        result = await fallback()
        ctx.logger.info(f"[bus] ↺ fallback done for {name}")
        return result


# ── module-level singleton (populated in run.py) ───────────────────────

_bus: Optional[AgentBus] = None


def init_bus(addresses: Dict[str, str], timeout: int = 15) -> AgentBus:
    global _bus
    _bus = AgentBus(addresses, timeout)
    return _bus


def get_bus() -> AgentBus:
    assert _bus is not None, "AgentBus not initialised — call init_bus() first"
    return _bus


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]
