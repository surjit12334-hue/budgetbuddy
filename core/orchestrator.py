"""Orchestrator: intent router + reply composer.

This is the brain's entry point.
In Phase 2 the DirectBus will be replaced by a real AgentBus,
but the public API — handle(session_id, text) → str — stays the same.
"""

import re
from datetime import datetime
from typing import Optional

from .models import Goal
from .state import SessionStore
from .parser import parse_any
from .categorizer import Categorizer
from .analyzer import Analyzer, is_subscription, is_bill
from .llm import LLMClient
from .coach import Coach
from .goal import GoalCalculator
from .splitter import SplitCalculator
from .payments import PaymentManager
from .cards import CardBuilder

# ──────────────────────── intent constants ────────────────────────────

INGEST = "ingest"
ANALYSIS = "analysis"
SUBSCRIPTIONS = "subscriptions"
GOAL = "goal"
SPLIT = "split"
PAYMENT = "payment"
HELP = "help"

_MONTHS = (
    "january|february|march|april|may|june|"
    "july|august|september|october|november|december"
)


class Orchestrator:
    def __init__(self):
        self.store = SessionStore()
        self.llm = LLMClient()
        self.categorizer = Categorizer(self.llm)
        self.analyzer = Analyzer()
        self.coach = Coach(self.llm)
        self.goal_calc = GoalCalculator()
        self.splitter = SplitCalculator()
        self.payments = PaymentManager()
        self.cards = CardBuilder()

    # ──────────────────── intent detection ─────────────────────────────

    def _detect_intent(self, text: str) -> str:
        # Multi-line / CSV-looking input → ingest regardless of keywords
        if text.count("\n") >= 2:
            return INGEST
        # A single line with a date + amount pattern is also ingest
        if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", text) and re.search(
            r"\d+\.\d{2}", text
        ):
            return INGEST

        low = text.lower().strip()

        # Priority order: most specific first
        if re.search(r"\b(split|owe|share the bill|who pays|settle)\b", low):
            return SPLIT

        if re.search(rf"\b(save|saving|goal|target)\b.*\$\d+|by\s+({_MONTHS})", low):
            return GOAL

        if re.search(r"\b(subscriptions?|recurring|monthly charge|renewals?)\b", low):
            return SUBSCRIPTIONS

        if re.search(r"\b(how am i doing|analysis|report|breakdown|spending|summary|health|overview)\b", low):
            return ANALYSIS

        if re.search(r"\b(pro|upgrade|premium|unlock|payment|lifetime)\b", low):
            return PAYMENT

        if re.search(r"\b(help|what can you do|commands|hi|hello|hey|start)\b", low):
            return HELP

        return HELP

    # ──────────────────── public entry point ───────────────────────────

    def handle(self, session_id: str, text: str) -> str:
        self.store.get_or_create(session_id)
        intent = self._detect_intent(text)

        handlers = {
            INGEST: self._handle_ingest,
            ANALYSIS: self._handle_analysis,
            SUBSCRIPTIONS: self._handle_subscriptions,
            GOAL: self._handle_goal,
            SPLIT: self._handle_split,
            PAYMENT: self._handle_payment,
            HELP: self._handle_help,
        }

        reply = handlers[intent](session_id, text)

        # Persist conversation history
        self.store.add_message(session_id, "user", text)
        self.store.add_message(session_id, "assistant", reply)

        return reply

    # ──────────────────── handlers ─────────────────────────────────────

    def _handle_ingest(self, session_id: str, text: str) -> str:
        transactions = parse_any(text)
        if not transactions:
            return (
                "I couldn't find any transactions in that text. "
                "Try pasting a CSV or listing transactions one per line."
            )

        self.categorizer.categorize_all(transactions)
        self.store.save_transactions(session_id, transactions)

        income = sum(t.amount for t in transactions if t.amount > 0)
        expenses = sum(abs(t.amount) for t in transactions if t.amount < 0)

        return (
            f"✅ Parsed {len(transactions)} transactions!\n\n"
            f"💰 Income found:  ${income:,.2f}\n"
            f"💸 Expenses found: ${expenses:,.2f}\n\n"
            'Ask me "how am I doing?" for a full analysis, or '
            '"what subscriptions do I have?" to see recurring charges.'
        )

    def _handle_analysis(self, session_id: str, _text: str = "") -> str:
        txns = self.store.load_transactions(session_id)
        if not txns:
            return "I don't have any transactions yet. Paste your spending data first!"

        analysis = self.analyzer.analyze(txns)
        report = self.analyzer.get_report(analysis)
        coach_msg = self.coach.get_insights(analysis)
        return f"{report}\n\n{'─' * 40}\n\n{coach_msg}"

    def _handle_subscriptions(self, session_id: str, _text: str = "") -> str:
        txns = self.store.load_transactions(session_id)
        if not txns:
            return "I need your transaction data first. Paste it and I'll find your subscriptions!"

        analysis = self.analyzer.analyze(txns)
        # Discretionary subscriptions only — rent/utilities recur too but
        # are bills, not something you can "cancel".
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

        # Bills recur too, but you can't "cancel" your rent — reporting
        # them separately keeps the subscription total honest.
        if bills:
            if lines:
                lines.append("")
            bill_total = sum(b["amount"] for b in bills)
            lines += [
                "── Fixed Bills (not subscriptions) ──",
                "",
            ]
            for b in bills:
                lines.append(f"  {b['merchant']:<22} ${b['amount']:>8,.2f}/mo")
            lines += [
                "",
                f"  {'TOTAL':<22} ${bill_total:>8,.2f}/mo",
                "",
                "💡 These are recurring obligations, not subscriptions.",
            ]

        return "\n".join(lines)

    def _handle_goal(self, session_id: str, text: str) -> str:
        # Extract target amount
        amt_match = re.search(r"\$?\s*([\d,]+(?:\.\d{2})?)", text)
        if not amt_match:
            return "Tell me your savings goal, e.g. 'I want to save $3000 by August'."

        target = float(amt_match.group(1).replace(",", ""))

        # Extract deadline month
        month_match = re.search(rf"\b({_MONTHS})\b", text.lower())
        deadline: Optional[datetime] = None
        if month_match:
            month_num = [
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
            ].index(month_match.group(1)) + 1
            now = datetime.now()
            year = now.year + (1 if month_num < now.month else 0)
            deadline = datetime(year, month_num, 1)

        if deadline is None:
            # Default: 6 months out
            now = datetime.now()
            m = now.month + 6
            y = now.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            deadline = datetime(y, m, 1)

        goal = Goal(target_amount=target, deadline=deadline)

        # Pull income / expenses for gap analysis
        txns = self.store.load_transactions(session_id)
        income = expenses = 0.0
        if txns:
            a = self.analyzer.analyze(txns)
            income, expenses = a.total_income, a.total_expenses

        result = self.goal_calc.calculate(goal, income, expenses)
        return self.goal_calc.format_response(result)

    def _handle_split(self, session_id: str, text: str) -> str:
        amt_match = re.search(r"\$?\s*([\d,]+(?:\.\d{2})?)", text)
        if not amt_match:
            return "Tell me the total amount to split, e.g. 'Split this $90 dinner with Alice and Bob'."

        amount = float(amt_match.group(1).replace(",", ""))

        # Extract names after "with" / "between" / "among"
        names: list = []
        name_match = re.search(
            r"(?:with|between|among)\s+(.+?)(?:\?|$)", text, re.IGNORECASE
        )
        if name_match:
            names = [
                n.strip().title()
                for n in re.split(r"\s+and\s+|,\s*|\s+", name_match.group(1))
                if n.strip()
            ]

        if "you" not in [n.lower() for n in names]:
            names.insert(0, "You")

        shares = self.splitter.even_split(amount, names)
        return self.splitter.format_split(
            text.split("split", 1)[-1].strip(" ?!.") or "Bill", amount, shares
        )

    def _handle_payment(self, session_id: str, _text: str = "") -> str:
        req = self.payments.create_pro_request()
        return self.payments.format_request(req)

    @staticmethod
    def _handle_help(_session_id: str = "", _text: str = "") -> str:
        return (
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
