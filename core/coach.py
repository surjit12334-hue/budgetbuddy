"""Coach: LLM-powered insights with deterministic fallback.

Privacy rule: only aggregate figures are ever sent to the LLM —
raw transaction lines never leave the machine.
"""

from typing import Optional

from .analyzer import AnalysisResult, is_subscription
from .llm import LLMClient

COACH_SYSTEM_PROMPT = """\
You are BudgetBuddy, a friendly and insightful personal-finance coach.
You analyse spending patterns and provide actionable advice.

Key principles:
- Be specific and actionable.
- Be encouraging but honest.
- Use ONLY the aggregate data provided (never request raw transactions).
- Keep responses concise (2-4 sentences per point).
- Focus on the most impactful improvements first.
- Use a warm, conversational tone.
"""


class Coach:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    # ── public ────────────────────────────────────────────────────────

    def get_insights(self, analysis: AnalysisResult) -> str:
        if self.llm and self.llm.available:
            text = self._llm_insights(analysis)
            if text:
                return text
        return self._fallback_insights(analysis)

    # ── LLM path ──────────────────────────────────────────────────────

    def _llm_insights(self, analysis: AnalysisResult) -> Optional[str]:
        cat_lines = "\n".join(
            f"  - {c}: ${a:,.2f}"
            for c, a in analysis.top_categories
            if c != "income"
        )
        sub_lines = "\n".join(
            f"  - {r['merchant']}: ${r['amount']:,.2f}/mo"
            for r in analysis.recurring_items
            if is_subscription(r)
        ) or "  (none detected)"

        prompt = f"""\
{COACH_SYSTEM_PROMPT}

Based on this financial analysis, provide 3-5 brief coaching insights and a
revised budget suggestion (50/30/20 rule).

Financial Summary:
- Total Income:      ${analysis.total_income:,.2f}
- Total Expenses:    ${analysis.total_expenses:,.2f}
- Net:               ${analysis.net:,.2f}
- Savings Rate:      {analysis.savings_rate:.1f}%
- Fixed Expenses:    ${analysis.fixed_expenses:,.2f}
- Variable Expenses: ${analysis.variable_expenses:,.2f}
- Needs:             ${analysis.needs:,.2f}
- Wants:             ${analysis.wants:,.2f}

Spending by Category:
{cat_lines}

Recurring Charges:
{sub_lines}
"""
        return self.llm.generate(prompt)

    # ── deterministic fallback ────────────────────────────────────────

    def _fallback_insights(self, analysis: AnalysisResult) -> str:
        lines = ["**BudgetBuddy Coach** (offline mode)", ""]

        # Savings
        if analysis.savings_rate < 0:
            lines.append(
                "⚠️ You're spending more than you earn. "
                "Focus on reducing your biggest expense category."
            )
        elif analysis.savings_rate < 20:
            lines.append(
                f"💡 Your savings rate is {analysis.savings_rate:.1f}%. "
                "Aim for 20%+ by trimming variable expenses."
            )
        else:
            lines.append(
                f"🎉 Excellent savings rate of {analysis.savings_rate:.1f}%! "
                "Keep maintaining this habit."
            )

        # Top category
        if analysis.top_categories:
            top_cat, top_amt = analysis.top_categories[0]
            if top_cat != "income":
                lines.append(
                    f"📊 Your biggest expense: {top_cat} (${top_amt:,.2f}). "
                    "Set a monthly cap here."
                )

        # Subscriptions — discretionary only (mirrors analyzer.is_subscription).
        subs = [s for s in analysis.recurring_items if is_subscription(s)]
        if subs:
            total = sum(s["amount"] for s in subs)
            lines.append(
                f"🔁 {len(subs)} subscription(s) costing ${total:,.2f}/mo. "
                "Cancel any you're not using."
            )

        # 50/30/20 budget
        if analysis.total_income > 0:
            needs = analysis.total_income * 0.50
            wants = analysis.total_income * 0.30
            savings = analysis.total_income * 0.20
            lines.append("")
            lines.append("**Suggested Budget (50/30/20):**")
            lines.append(
                f"  Needs: ${needs:,.2f}  |  "
                f"Wants: ${wants:,.2f}  |  "
                f"Savings: ${savings:,.2f}"
            )

        return "\n".join(lines)
