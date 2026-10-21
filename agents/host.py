"""Host agent: ACP entry point.

Receives Query via REST POST /submit, detects intent, routes to the
correct sub-agent through the AgentBus (15 s timeout), and falls back
to in-process core modules when a sub-agent is unreachable.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from uagents import Agent, Context, Model
from uagents.protocol import Protocol
from uagents_core.contrib.protocols.chat import (
    ChatMessage, ChatAcknowledgement, TextContent, StartSessionContent,
    EndSessionContent, MetadataContent, chat_protocol_spec,
)

from core.parser import parse_any
from core.models import Goal
from core.analyzer import is_subscription, is_bill
from typing import Dict

from .messages import (
    Query, Response, HealthResponse,
    IngestRequest, IngestResponse,
    AnalysisRequest, AnalysisResponse,
    CoachRequest, CoachResponse,
    GoalRequest, GoalResponse,
    SplitRequest, SplitResponse,
)
from .bus import get_bus, new_request_id
from .services import (
    store, categorizer, analyzer, coach, goal_calc, splitter, cards, payments,
)

# ── intent constants (kept in sync with core.orchestrator) ────────────

INGEST = "ingest"
ANALYSIS = "analysis"
INSIGHTS = "insights"
SUBSCRIPTIONS = "subscriptions"
GOAL = "goal"
SPLIT = "split"
PAYMENT = "payment"
HELP = "help"

_MONTHS = (
    "january|february|march|april|may|june|"
    "july|august|september|october|november|december"
)


def detect_intent(text: str) -> str:
    if text.count("\n") >= 2:
        return INGEST
    if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", text) and re.search(r"\d+\.\d{2}", text):
        return INGEST

    low = text.lower().strip()
    if re.search(r"\b(split|owe|share the bill|who pays|settle)\b", low):
        return SPLIT
    if re.search(rf"\b(save|saving|goal|target)\b.*\$\d+|by\s+({_MONTHS})", low):
        return GOAL
    if re.search(r"\b(subscriptions?|recurring|monthly charge|renewals?)\b", low):
        return SUBSCRIPTIONS
    # Advice-seeking language gets the insights carousel; a plain status
    # question gets the dashboard. Both run the same analysis — only the
    # card differs.
    if re.search(r"\b(tips?|advice|advise|insights?|suggestions?|recommend\w*|improve|where can i)\b", low):
        return INSIGHTS
    if re.search(r"\b(how am i doing|analysis|report|breakdown|spending|summary|health|overview)\b", low):
        return ANALYSIS
    if re.search(r"\b(pro|upgrade|premium|unlock|payment|lifetime)\b", low):
        return PAYMENT
    if re.search(r"\b(help|what can you do|commands|hi|hello|hey|start)\b", low):
        return HELP
    return HELP


# ── host agent ─────────────────────────────────────────────────────────

host_agent = Agent(
    name="host",
    seed="budgetbuddy host agent seed v1",
    log_level="INFO",
    # Agentverse mailbox: the agent dials out to Agentverse, so it is
    # reachable from ASI:One with NO public URL / tunnel required.
    mailbox=os.environ.get("ENABLE_MAILBOX", "true").lower() == "true",
    agentverse=os.environ.get("ENABLE_AGENTVERSE", "true").lower() == "true",
    # Publish a human-readable profile on Agentverse (Phase 5.2).
    description=(
        "BudgetBuddy — a multi-agent personal-finance coach. Paste your bank "
        "data, get analysis, find forgotten subscriptions, set savings goals, "
        "split bills, and unlock Pro — all in chat."
    ),
    publish_agent_details=True,
)

# uAgents reserves /submit for envelope routing and blocks REST
# registration on reserved paths.  We temporarily flip _init_done so
# the decorator runs, then restore it.  The ASGI server checks
# localhost before serving reserved paths, so external curl still works.
host_agent._init_done = False

# Chat Protocol — how ASI:One actually talks to agents.
_chat_proto = Protocol(spec=chat_protocol_spec)


# ── chat protocol handler (ASI:One) ───────────────────────────────────

def _parse_card_selection(text: str) -> Optional[Dict]:
    """Return a card selection dict, or None if this isn't one.

    Per the ASI:One docs the shape depends on how the user reached the
    agent: direct @mention sends the selection as JSON verbatim, while
    the planner narrates it in prose. We try JSON first and let anything
    that isn't a recognisable selection fall through to normal routing.
    """
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict) and "action" in data:
        return data
    return None


def _selection_to_instruction(sel: Dict) -> str:
    """Map a card selection to text the normal intent router understands."""
    action = str(sel.get("action", ""))
    mapping = {
        "confirm_payment": "How do I unlock Pro?",
        "cancel_payment": "What subscriptions do I have?",
        "onboarding_submit": "How am I doing?",
        "review_subscription": "What subscriptions do I have?",
        "remind_all": "How am I doing?",
        "dismiss_insight": "How am I doing?",
        "settle_share": "How am I doing?",
    }
    return mapping.get(action, "Help")


@_chat_proto.on_message(ChatAcknowledgement)
async def _on_chat_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
    ctx.logger.debug(f"[chat] ack from {sender} for {msg.acknowledged_msg_id}")


@_chat_proto.on_message(ChatMessage)
async def _handle_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
    """Handle a Chat Protocol message from ASI:One.

    Every chat session maps to one BudgetBuddy session_id, so multi-turn
    memory ("How am I doing?" after pasting data) works exactly as it
    does locally.
    """
    # 1. Acknowledge receipt (required by the chat protocol).
    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id
        ),
    )

    # 2. Collect the text parts and any session-end signal.
    text_parts: list[str] = []
    end_session = False
    for item in msg.content:
        if isinstance(item, TextContent):
            text_parts.append(item.text)
        elif isinstance(item, EndSessionContent):
            end_session = True
        elif isinstance(item, StartSessionContent):
            ctx.logger.info(f"[chat] start-session from {sender}")

    text = "\n".join(text_parts).strip()
    sid = f"asi1-{sender}"

    # A card button click arrives as a selection, either verbatim JSON
    # (direct @mention) or narrated prose (planner-mediated). Turn the
    # JSON case into a readable instruction so it routes normally.
    card_action = _parse_card_selection(text)
    if card_action:
        ctx.logger.info(f"[cards] ← selection {card_action}")
        text = _selection_to_instruction(card_action)

    ctx.logger.info(f"[chat] ← asi1  session={sid}  text={text[:60]!r}")

    if not text:
        reply = "Send me your transactions, or ask 'How am I doing?' for a summary."
    else:
        reply = await route(ctx, sid, text)
    ctx.logger.info(f"[chat] → asi1  {len(reply)} chars")

    # 3. Send the reply.  If the user ended the session, attach the
    #    EndSessionContent marker so ASI:One closes cleanly.
    content = [TextContent(type="text", text=reply)]

    # 3b. Attach an interactive card when the intent has one. Cards are
    #     additive: the text above is always sent, so a rejected card
    #     degrades to plain text rather than losing the answer.
    if text and not end_session:
        meta = _card_for_intent(detect_intent(text), sid, logger=ctx.logger)
        if meta:
            content.append(MetadataContent(type="metadata", metadata=meta))
            ctx.logger.info(f"[cards] attached  kind={meta['card_kind']}")

    if end_session:
        content.append(EndSessionContent(type="end-session"))
    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.now(timezone.utc), msg_id=uuid.uuid4(), content=content
        ),
    )


# Publish the chat-protocol MANIFEST, not just its digest. Without this
# the Almanac record shows "metadata: None" and the agent advertises a
# protocol digest with no description of how to talk to it — which is
# what ASI:One uses to decide whether the agent can be chatted with.
# https://uagents.fetch.ai/docs/guides/public_private_agents
host_agent.include(_chat_proto, publish_manifest=True)


# ── interactive cards (Phase 6) ───────────────────────────────────────
#
# route() returns plain markdown and is shared by REST and chat, so cards
# are attached HERE, in the chat layer only — REST/testing is unaffected.
# Cards are additive: the markdown reply is always sent; a card is an
# extra MetadataContent block. If the payload is rejected (or cards are
# off) ASI:One silently falls back to the text, so there is no failure
# mode where the user sees nothing.


def _card_for_intent(intent: str, session_id: str, analysis=None, logger=None) -> Dict[str, str]:
    """Return ASI:One card metadata for an intent, or {} for none.

    Never raises: a card is a bonus, and a bug here must not cost the
    user their answer.
    """
    if not cards.enabled:
        return {}
    try:
        if intent == ANALYSIS:
            txns = store.load_transactions(session_id)
            if not txns:
                return {}
            result = analysis or analyzer.analyze(txns)
            return cards.as_metadata(
                "custom", cards.build_dashboard(result),
                is_terminal=True, drawer_width_px=560,
            )

        if intent == INSIGHTS:
            txns = store.load_transactions(session_id)
            if not txns:
                return {}
            result = analysis or analyzer.analyze(txns)
            if not result.insights:
                return {}
            return cards.as_metadata(
                "carousel", cards.build_insights_carousel(result.insights),
                is_terminal=True, drawer_width_px=640,
            )

        if intent == SUBSCRIPTIONS:
            txns = store.load_transactions(session_id)
            if not txns:
                return {}
            result = analysis or analyzer.analyze(txns)
            meta = cards.as_metadata(
                "carousel", cards.build_subscriptions_card(result),
                drawer_width_px=640,
            )
            # An empty carousel is a broken card — send text only.
            return meta if result.recurring_items else {}

        if intent == GOAL:
            txns = store.load_transactions(session_id)
            if not txns:
                return {}
            plan = _last_goal_plan.get(session_id)
            if not plan:
                return {}
            return cards.as_metadata(
                "custom", cards.build_goal_card(plan),
                is_terminal=True, drawer_width_px=560,
            )

        if intent == PAYMENT:
            req = payments.create_pro_request()
            from core.payments import PRO_PRICE, PRO_DESCRIPTION
            return cards.as_metadata(
                "review",
                cards.build_checkout_card(req.id, PRO_PRICE, PRO_DESCRIPTION),
                drawer_width_px=600,
            )

    except Exception as exc:  # pragma: no cover - defensive by design
        # A broken card must never cost the user their answer: log, then
        # fall through to the markdown reply that was already computed.
        if logger is not None:
            logger.warning(f"[cards] build failed for {intent}: {exc}")
        return {}
    return {}


# The goal plan is computed inside route(); stash it so the card layer can
# render it without recomputing (and without parsing the markdown back).
_last_goal_plan: Dict[str, Dict] = {}


def _remember_goal_plan(session_id: str, plan_text: str, text: str) -> None:
    """Record minimal goal facts for the card. Best-effort, never fatal."""
    try:
        m = re.search(r"\$?\s*([\d,]+(?:\.\d{2})?)", text)
        target = float(m.group(1).replace(",", "")) if m else 0.0
        mm = re.search(r"Monthly savings needed:\s*\$([\d,]+\.\d{2})", plan_text)
        monthly = float(mm.group(1).replace(",", "")) if mm else 0.0
        dm = re.search(r"by\s+([A-Za-z]+\s+\d{4})", plan_text)
        _last_goal_plan[session_id] = {
            "target_amount": target,
            "monthly_target": monthly,
            "deadline": dm.group(1) if dm else "—",
            "on_track": "on track" in plan_text.lower(),
        }
    except Exception:
        pass


# ── fallbacks (in-process, no agent involved) ──────────────────────────

async def _fallback_ingest(session_id: str, text: str) -> IngestResponse:
    txns = parse_any(text)
    categorizer.categorize_all(txns)
    store.save_transactions(session_id, txns)
    income = sum(t.amount for t in txns if t.amount > 0)
    expenses = sum(abs(t.amount) for t in txns if t.amount < 0)
    reply = (
        f"✅ Parsed {len(txns)} transactions!\n\n"
        f"💰 Income found:   ${income:,.2f}\n"
        f"💸 Expenses found: ${expenses:,.2f}\n\n"
        'Ask me "how am I doing?" for a full analysis, or '
        '"what subscriptions do I have?" to see recurring charges.'
    )
    return IngestResponse(request_id="fallback", reply=reply, txn_count=len(txns))


async def _fallback_analysis(session_id: str) -> AnalysisResponse:
    txns = store.load_transactions(session_id)
    if not txns:
        return AnalysisResponse(
            request_id="fallback",
            report="I don't have any transactions yet. Paste your spending data first!",
            insights="",
        )
    analysis = analyzer.analyze(txns)
    report = analyzer.get_report(analysis)
    coach_msg = coach.get_insights(analysis)
    return AnalysisResponse(request_id="fallback", report=report, insights=coach_msg)


async def _fallback_coach(session_id: str) -> CoachResponse:
    txns = store.load_transactions(session_id)
    if not txns:
        return CoachResponse(
            request_id="fallback",
            message="I need your data first — paste your transactions!",
        )
    analysis = analyzer.analyze(txns)
    message = coach.get_insights(analysis)
    return CoachResponse(request_id="fallback", message=message)


async def _fallback_goal(session_id: str, text: str) -> GoalResponse:
    amt_match = re.search(r"\$?\s*([\d,]+(?:\.\d{2})?)", text)
    if not amt_match:
        return GoalResponse(
            request_id="fallback",
            plan="Tell me your savings goal, e.g. 'I want to save $3000 by August'.",
        )
    target = float(amt_match.group(1).replace(",", ""))
    month_match = re.search(rf"\b({_MONTHS})\b", text.lower())
    now = datetime.now()
    if month_match:
        month_num = [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ].index(month_match.group(1)) + 1
        year = now.year + (1 if month_num < now.month else 0)
        deadline = datetime(year, month_num, 1)
    else:
        m = now.month + 6
        y = now.year + (m - 1) // 12
        deadline = datetime(y, (m - 1) % 12 + 1, 1)

    goal = Goal(target_amount=target, deadline=deadline)
    txns = store.load_transactions(session_id)
    income = expenses = 0.0
    if txns:
        a = analyzer.analyze(txns)
        income, expenses = a.total_income, a.total_expenses
    result = goal_calc.calculate(goal, income, expenses)
    plan = goal_calc.format_response(result)
    return GoalResponse(request_id="fallback", plan=plan)


async def _fallback_split(text: str) -> SplitResponse:
    amt_match = re.search(r"\$?\s*([\d,]+(?:\.\d{2})?)", text)
    if not amt_match:
        return SplitResponse(
            request_id="fallback",
            result="Tell me the total amount, e.g. 'Split this $90 dinner with Alice and Bob'.",
        )
    amount = float(amt_match.group(1).replace(",", ""))
    names: list = []
    name_match = re.search(r"(?:with|between|among)\s+(.+?)(?:\?|$)", text, re.IGNORECASE)
    if name_match:
        names = [
            n.strip().title()
            for n in re.split(r"\s+and\s+|,\s*|\s+", name_match.group(1))
            if n.strip()
        ]
    if "you" not in [n.lower() for n in names]:
        names.insert(0, "You")
    shares = splitter.even_split(amount, names)
    label = text.split("split", 1)[-1].strip(" ?!.") or "Bill"
    result = splitter.format_split(label, amount, shares)
    return SplitResponse(request_id="fallback", result=result)


# ── static replies (no sub-agent needed) ──────────────────────────────

_SUBSCRIPTIONS_PROMPT = "Paste your transaction data first — I'll find your subscriptions!"

_HELP_TEXT = (
    "═══ BudgetBuddy Help ═══\n\n"
    "I'm your AI budget coach! Here's what I can do:\n\n"
    "📋 **Paste your spending data** — CSV or free-text, I'll parse it\n"
    '📊 **"How am I doing?"** — Get a full financial health report\n'
    '🔁 **"What subscriptions do I have?"** — Find recurring charges\n'
    '🎯 **"Save $3000 by August"** — Get a savings goal plan\n'
    '👥 **"Split $90 dinner with Alice"** — Calculate bill splits\n'
    '💎 **"Unlock Pro"** — See premium features\n\n'
    "Just paste your data or ask a question!"
)


def _subscriptions_reply(session_id: str) -> str:
    txns = store.load_transactions(session_id)
    if not txns:
        return _SUBSCRIPTIONS_PROMPT

    analysis = analyzer.analyze(txns)
    # Discretionary subscriptions only — rent/utilities recur too but are
    # bills, not something you can "cancel".
    subs = [s for s in analysis.recurring_items if is_subscription(s)]
    bills = [s for s in analysis.recurring_items if is_bill(s)]

    if not subs and not bills:
        return (
            "I didn't find any obvious recurring charges in your data. "
            "They might be mixed with other charges."
        )

    lines: list[str] = []

    if subs:
        lines += ["═══ Recurring Subscriptions ═══", ""]
        total = 0.0
        for s in subs:
            lines.append(f"  {s['merchant']:<22} ${s['amount']:>8,.2f}/mo")
            total += s["amount"]
        lines += [
            "",
            f"  {'TOTAL':<22} ${total:>8,.2f}/mo",
            f"  {'ANNUAL':<22} ${total * 12:>8,.2f}/yr",
            "",
            f"💡 You have {len(subs)} subscription(s). Review which ones you actually use!",
        ]

    if bills:
        if lines:
            lines.append("")
        bill_total = sum(b["amount"] for b in bills)
        lines += ["── Fixed Bills (not subscriptions) ──", ""]
        for b in bills:
            lines.append(f"  {b['merchant']:<22} ${b['amount']:>8,.2f}/mo")
        lines += [
            "",
            f"  {'TOTAL':<22} ${bill_total:>8,.2f}/mo",
            "",
            "💡 These are recurring obligations, not subscriptions.",
        ]

    return "\n".join(lines)


def _payment_reply() -> str:
    from core.payments import PRO_PRICE, PRO_DESCRIPTION
    from .services import payments
    req = payments.create_pro_request()
    return payments.format_request(req)


# ── routing (shared by the REST endpoint and the chat protocol) ───────
async def route(ctx: Context, session_id: str, text: str) -> str:
    """Detect intent, route to the right sub-agent, return a reply string.

    Used by both the local REST endpoint and the ASI:One chat handler,
    so every transport sees identical behaviour.
    """
    intent = detect_intent(text)
    ctx.logger.info(f"[host] intent: {intent}")
    bus = get_bus()
    sid = session_id

    # ── INGEST ──
    if intent == INGEST:
        resp = await bus.call(
            ctx, "ingest",
            IngestRequest(request_id=new_request_id(), session_id=sid, text=text),
            IngestResponse,
            fallback=lambda: _fallback_ingest(sid, text),
        )
        return resp.reply if resp else "Sorry, I couldn't parse that."

    # ── ANALYSIS / INSIGHTS ──
    # Same analysis run; the two intents differ only in which card the
    # chat layer attaches (dashboard vs. insights carousel).
    if intent in (ANALYSIS, INSIGHTS):
        resp = await bus.call(
            ctx, "analyst",
            AnalysisRequest(request_id=new_request_id(), session_id=sid),
            AnalysisResponse,
            fallback=lambda: _fallback_analysis(sid),
        )
        if resp is None:
            return "Sorry, analysis is unavailable right now."
        return f"{resp.report}\n\n{'─' * 40}\n\n{resp.insights}" if resp.insights else resp.report

    # ── SUBSCRIPTIONS (handled in-process — needs full analysis) ──
    if intent == SUBSCRIPTIONS:
        ctx.logger.info("[host] handling subscriptions in-process")
        return _subscriptions_reply(sid)

    # ── GOAL ──
    if intent == GOAL:
        resp = await bus.call(
            ctx, "goal",
            GoalRequest(request_id=new_request_id(), session_id=sid, text=text),
            GoalResponse,
            fallback=lambda: _fallback_goal(sid, text),
        )
        plan = resp.plan if resp else "Sorry, I couldn't compute that goal."
        _remember_goal_plan(sid, plan, text)
        return plan

    # ── SPLIT ──
    if intent == SPLIT:
        resp = await bus.call(
            ctx, "splitter",
            SplitRequest(request_id=new_request_id(), text=text),
            SplitResponse,
            fallback=lambda: _fallback_split(text),
        )
        return resp.result if resp else "Sorry, I couldn't split that."

    # ── PAYMENT (in-process) ──
    if intent == PAYMENT:
        ctx.logger.info("[host] handling payment in-process")
        return _payment_reply()

    # ── HELP ──
    return _HELP_TEXT


# ── REST handler (local testing / curl only) ──────────────────────────

@host_agent.on_rest_post("/submit", Query, Response)
async def _submit(ctx: Context, req: Query) -> Response:
    ctx.logger.info(f"[host] ← external  session={req.session_id}  text={req.text[:60]!r}")
    return Response(reply=await route(ctx, req.session_id, req.text))


# ── health endpoint (preflight / uptime monitoring) ───────────────────

@host_agent.on_rest_get("/health", HealthResponse)
async def _health(ctx: Context) -> HealthResponse:
    from .subagents import (
        ingest_agent, analyst_agent, coach_agent,
        goal_agent, splitter_agent,
    )
    return HealthResponse(
        status="ok",
        agents={
            "host": host_agent.address,
            "ingest": ingest_agent.address,
            "analyst": analyst_agent.address,
            "coach": coach_agent.address,
            "goal": goal_agent.address,
            "splitter": splitter_agent.address,
        },
        session_ttl_hours=int(os.environ.get("SESSION_TTL_HOURS", "24")),
    )


# Restore init flag (see comment above)
host_agent._init_done = True
