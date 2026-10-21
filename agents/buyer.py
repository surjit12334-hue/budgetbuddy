"""BudgetBuddy buyer agent — the other half of the payment loop.

The host agent is the *seller*: it issues a ``RequestPayment`` for Pro
access.  This agent is the *buyer*: it receives that request and
commits to paying, so the full Agent Payment Protocol exchange can be
demonstred end to end without any external service.

    RequestPayment  (host → buyer)
    CommitPayment   (buyer → host)
    CompletePayment (host → buyer)

Run it next to the Bureau:

    .venv/bin/python -m agents.buyer

It then talks to the host agent over the uAgents network (localhost),
signs the challenge with its own identity, and waits for the host's
``CompletePayment``.  The host verifies the signature against this
agent's ``agent1q...`` address before unlocking Pro.

Reference:
    https://innovationlab.fetch.ai/resources/docs/agent-transaction/agent-payment-protocol
"""

import asyncio
import os
import sys

# Python 3.14 requires an event loop to exist before uagents imports.
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

from datetime import datetime, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402

from uagents import Agent, Context, Protocol  # noqa: E402
from uagents_core.contrib.protocols.chat import (  # noqa: E402
    ChatMessage, TextContent,
)
from uagents_core.contrib.protocols.payment import (  # noqa: E402
    CommitPayment, RejectPayment, RequestPayment,
    CompletePayment, CancelPayment, payment_protocol_spec,
)
from uagents_core.identity import Identity  # noqa: E402

from core.payments import (  # noqa: E402
    BB_METADATA_KEY, sign_commitment,
)

BUYER_PORT = int(os.environ.get("BUYER_PORT", "8012"))
HOST_ADDRESS = os.environ.get("HOST_ADDRESS", "")
BUYER_SEED = os.environ.get("BUYER_SEED", "budgetbuddy buyer agent seed v1")

# transaction_id → {seller, reference} for the requests we are answering.
pending: dict = {}


buyer_agent = Agent(
    name="budgetbuddy_buyer",
    seed=BUYER_SEED,
    port=BUYER_PORT,
    endpoint=[f"http://127.0.0.1:{BUYER_PORT}/submit"],
)

# The same derivation uAgents uses for the agent's own identity
# (Agent._initialize_wallet_and_identity → Identity.from_seed(seed, 0)),
# obtained through the public API rather than the private attribute.
buyer_identity = Identity.from_seed(BUYER_SEED, 0)

payment_proto = Protocol(spec=payment_protocol_spec, role="buyer")


@payment_proto.on_message(RequestPayment)
async def _on_request(ctx: Context, sender: str, msg: RequestPayment) -> None:
    """A seller asked us to pay.  Commit to it."""
    ctx.logger.info(f"[buyer] ← RequestPayment from {sender}")
    ctx.logger.info(f"[buyer]   amount={msg.accepted_funds}")

    if not msg.accepted_funds:
        await ctx.send(sender, RejectPayment(reason="no accepted funds provided"))
        return

    funds = msg.accepted_funds[0]
    metadata = msg.metadata or {}
    bb = metadata.get(BB_METADATA_KEY) or {}

    # The challenge the seller wants signed.  Signing it proves this
    # buyer committed to this exact request; the seller verifies the
    # signature against our agent address.
    challenge = bb.get("challenge", "")
    signature = ""
    if challenge:
        signature = sign_commitment(challenge, buyer_identity)
        ctx.logger.info("[buyer]   signed the seller's challenge")

    transaction_id = f"bb-{uuid4().hex[:16]}"
    commit = CommitPayment(
        funds=funds,
        recipient=msg.recipient,
        transaction_id=transaction_id,
        reference=msg.reference,
        description=msg.description,
        metadata={
            BB_METADATA_KEY: {
                "reference": msg.reference or bb.get("reference", ""),
                "signature": signature,
            }
        },
    )
    pending[transaction_id] = {"seller": sender, "reference": msg.reference}
    await ctx.send(sender, commit)
    ctx.logger.info(f"[buyer] → CommitPayment ({transaction_id})")


@payment_proto.on_message(CompletePayment)
async def _on_complete(ctx: Context, sender: str, msg: CompletePayment) -> None:
    """The seller verified our payment."""
    ctx.logger.info(f"[buyer] ✓ CompletePayment from {sender} — payment accepted")
    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(
                type="text",
                text="Payment accepted — thanks! Pro is unlocked on my side too.",
            )],
        ),
    )


@payment_proto.on_message(CancelPayment)
async def _on_cancel(ctx: Context, sender: str, msg: CancelPayment) -> None:
    """The seller refused the commit."""
    ctx.logger.info(f"[buyer] ✗ CancelPayment from {sender}: {msg.reason}")


@buyer_agent.on_event("startup")
async def _on_startup(ctx: Context) -> None:
    ctx.logger.info(f"[buyer] address: {ctx.agent.address}")
    ctx.logger.info(f"[buyer] inspector: https://agentverse.ai/inspect/?uri="
                    f"http%3A//127.0.0.1%3A{BUYER_PORT}&address={ctx.agent.address}")
    if not HOST_ADDRESS:
        ctx.logger.warning(
            "[buyer] HOST_ADDRESS not set — set it to the host agent address "
            "so the buyer can find the seller."
        )


buyer_agent.include(payment_proto, publish_manifest=True)


if __name__ == "__main__":
    buyer_agent.run()
