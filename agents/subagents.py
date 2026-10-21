"""Sub-agents: Ingest, Analyst, Coach, Goal, Splitter.

Each wraps a core module and exposes it as an on_message handler.
All run inside the same Bureau process.
"""

import uuid
from datetime import datetime

from uagents import Agent, Context

from core.parser import parse_any
from core.models import Goal

from .messages import (
    IngestRequest, IngestResponse,
    AnalysisRequest, AnalysisResponse,
    CoachRequest, CoachResponse,
    GoalRequest, GoalResponse,
    SplitRequest, SplitResponse,
)
from .services import (
    store, categorizer, analyzer, coach, goal_calc, splitter,
)


# ── Ingest Agent ───────────────────────────────────────────────────────

ingest_agent = Agent(
    name="ingest",
    seed="budgetbuddy ingest agent seed v1",
    log_level="WARNING",
    # Sub-agents are internal (called via the AgentBus, never over HTTP).
    # Disabling the inspector keeps /agent_info unambiguous for the HOST,
    # which is what the Agentverse Inspector queries to create the mailbox.
    enable_agent_inspector=False,
)


@ingest_agent.on_message(IngestRequest, replies=IngestResponse)
async def _handle_ingest(ctx: Context, sender: str, msg: IngestRequest):
    ctx.logger.info(f"[ingest] ← host  parsing session={msg.session_id}")
    txns = parse_any(msg.text)
    categorizer.categorize_all(txns)
    store.save_transactions(msg.session_id, txns)

    income = sum(t.amount for t in txns if t.amount > 0)
    expenses = sum(abs(t.amount) for t in txns if t.amount < 0)
    reply = (
        f"✅ Parsed {len(txns)} transactions!\n\n"
        f"💰 Income found:   ${income:,.2f}\n"
        f"💸 Expenses found: ${expenses:,.2f}\n\n"
        'Ask me "how am I doing?" for a full analysis, or '
        '"what subscriptions do I have?" to see recurring charges.'
    )
    ctx.logger.info(f"[ingest] → host  {len(txns)} txns parsed")
    await ctx.send(sender, IngestResponse(
        request_id=msg.request_id,
        reply=reply,
        txn_count=len(txns),
    ))


# ── Analyst Agent ──────────────────────────────────────────────────────

analyst_agent = Agent(
    name="analyst",
    seed="budgetbuddy analyst agent seed v1",
    log_level="WARNING",
    # Sub-agents are internal (called via the AgentBus, never over HTTP).
    # Disabling the inspector keeps /agent_info unambiguous for the HOST,
    # which is what the Agentverse Inspector queries to create the mailbox.
    enable_agent_inspector=False,
)


@analyst_agent.on_message(AnalysisRequest, replies=AnalysisResponse)
async def _handle_analysis(ctx: Context, sender: str, msg: AnalysisRequest):
    ctx.logger.info(f"[analyst] ← host  session={msg.session_id}")
    txns = store.load_transactions(msg.session_id)
    if not txns:
        reply = "I don't have any transactions yet. Paste your spending data first!"
        await ctx.send(sender, AnalysisResponse(
            request_id=msg.request_id, report=reply, insights="",
        ))
        return

    analysis = analyzer.analyze(txns)
    report = analyzer.get_report(analysis)
    coach_msg = coach.get_insights(analysis)
    combined = f"{report}\n\n{'─' * 40}\n\n{coach_msg}"
    ctx.logger.info(f"[analyst] → host  {analysis.txn_count} txns analysed")
    await ctx.send(sender, AnalysisResponse(
        request_id=msg.request_id,
        report=report,
        insights=coach_msg,
    ))


# ── Coach Agent ────────────────────────────────────────────────────────

coach_agent = Agent(
    name="coach",
    seed="budgetbuddy coach agent seed v1",
    log_level="WARNING",
    # Sub-agents are internal (called via the AgentBus, never over HTTP).
    # Disabling the inspector keeps /agent_info unambiguous for the HOST,
    # which is what the Agentverse Inspector queries to create the mailbox.
    enable_agent_inspector=False,
)


@coach_agent.on_message(CoachRequest, replies=CoachResponse)
async def _handle_coach(ctx: Context, sender: str, msg: CoachRequest):
    ctx.logger.info(f"[coach] ← host  session={msg.session_id}")
    txns = store.load_transactions(msg.session_id)
    if not txns:
        await ctx.send(sender, CoachResponse(
            request_id=msg.request_id,
            message="I need your data first — paste your transactions!",
        ))
        return
    analysis = analyzer.analyze(txns)
    message = coach.get_insights(analysis)
    ctx.logger.info(f"[coach] → host  insights generated")
    await ctx.send(sender, CoachResponse(
        request_id=msg.request_id, message=message,
    ))


# ── Goal Agent ─────────────────────────────────────────────────────────

goal_agent = Agent(
    name="goal",
    seed="budgetbuddy goal agent seed v1",
    log_level="WARNING",
    # Sub-agents are internal (called via the AgentBus, never over HTTP).
    # Disabling the inspector keeps /agent_info unambiguous for the HOST,
    # which is what the Agentverse Inspector queries to create the mailbox.
    enable_agent_inspector=False,
)

_MONTHS = (
    "january|february|march|april|may|june|"
    "july|august|september|october|november|december"
)


@goal_agent.on_message(GoalRequest, replies=GoalResponse)
async def _handle_goal(ctx: Context, sender: str, msg: GoalRequest):
    import re
    ctx.logger.info(f"[goal] ← host  session={msg.session_id}")

    amt_match = re.search(r"\$?\s*([\d,]+(?:\.\d{2})?)", msg.text)
    if not amt_match:
        await ctx.send(sender, GoalResponse(
            request_id=msg.request_id,
            plan="Tell me your savings goal, e.g. 'I want to save $3000 by August'.",
        ))
        return

    target = float(amt_match.group(1).replace(",", ""))

    month_match = re.search(rf"\b({_MONTHS})\b", msg.text.lower())
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

    txns = store.load_transactions(msg.session_id)
    income = expenses = 0.0
    if txns:
        a = analyzer.analyze(txns)
        income, expenses = a.total_income, a.total_expenses

    result = goal_calc.calculate(goal, income, expenses)
    plan = goal_calc.format_response(result)
    ctx.logger.info(f"[goal] → host  monthly=${result.get('monthly_target', 0)}")
    await ctx.send(sender, GoalResponse(
        request_id=msg.request_id, plan=plan,
    ))


# ── Splitter Agent ─────────────────────────────────────────────────────

splitter_agent = Agent(
    name="splitter",
    seed="budgetbuddy splitter agent seed v1",
    log_level="WARNING",
    # Sub-agents are internal (called via the AgentBus, never over HTTP).
    # Disabling the inspector keeps /agent_info unambiguous for the HOST,
    # which is what the Agentverse Inspector queries to create the mailbox.
    enable_agent_inspector=False,
)


@splitter_agent.on_message(SplitRequest, replies=SplitResponse)
async def _handle_split(ctx: Context, sender: str, msg: SplitRequest):
    import re
    ctx.logger.info(f"[splitter] ← host")

    amt_match = re.search(r"\$?\s*([\d,]+(?:\.\d{2})?)", msg.text)
    if not amt_match:
        await ctx.send(sender, SplitResponse(
            request_id=msg.request_id,
            result="Tell me the total amount, e.g. 'Split this $90 dinner with Alice and Bob'.",
        ))
        return

    amount = float(amt_match.group(1).replace(",", ""))

    names: list = []
    name_match = re.search(
        r"(?:with|between|among)\s+(.+?)(?:\?|$)", msg.text, re.IGNORECASE
    )
    if name_match:
        names = [
            n.strip().title()
            for n in re.split(r"\s+and\s+|,\s*|\s+", name_match.group(1))
            if n.strip()
        ]
    if "you" not in [n.lower() for n in names]:
        names.insert(0, "You")

    shares = splitter.even_split(amount, names)
    label = msg.text.split("split", 1)[-1].strip(" ?!.") or "Bill"
    result = splitter.format_split(label, amount, shares)
    ctx.logger.info(f"[splitter] → host  {len(shares)} ways")
    await ctx.send(sender, SplitResponse(
        request_id=msg.request_id, result=result,
        description=label, total=amount, shares=shares,
    ))
