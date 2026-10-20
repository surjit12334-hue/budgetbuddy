"""Savings-goal what-if math."""

from datetime import datetime
from typing import Dict, Any, Optional

from .models import Goal


class GoalCalculator:
    def calculate(
        self,
        goal: Goal,
        monthly_income: float = 0.0,
        monthly_expenses: float = 0.0,
    ) -> Dict[str, Any]:
        now = datetime.now()

        if goal.deadline <= now:
            return {"error": "Deadline is in the past!"}

        # Months remaining (decimal)
        months = (goal.deadline.year - now.year) * 12 + (goal.deadline.month - now.month)
        if months < 1:
            months = max((goal.deadline - now).days / 30.0, 0.5)

        monthly_target = goal.target_amount / months

        result: Dict[str, Any] = {
            "target_amount": goal.target_amount,
            "deadline": goal.deadline.strftime("%B %Y"),
            "months_remaining": round(months, 1),
            "monthly_target": round(monthly_target, 2),
            "weekly_target": round(monthly_target * 12 / 52, 2),
            "daily_target": round(monthly_target * 12 / 365, 2),
        }

        # Gap analysis when we know income / expenses
        if monthly_income > 0:
            current_savings = monthly_income - monthly_expenses
            gap = monthly_target - current_savings

            if gap > 0:
                result["gap"] = round(gap, 2)
                result["on_track"] = False
                result["cut_scenarios"] = self._cut_scenarios(gap)
            else:
                result["on_track"] = True
                result["monthly_surplus"] = round(current_savings - monthly_target, 2)

        return result

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _cut_scenarios(needed: float) -> list:
        return [
            {
                "action": f"Cut dining/takeout by ${needed * 0.40:,.2f}/mo",
                "impact": "Cook at home 3 more times per week",
            },
            {
                "action": f"Cancel unused subscriptions (${needed * 0.20:,.2f}/mo)",
                "impact": "Review streaming services and app subscriptions",
            },
            {
                "action": f"Reduce shopping/entertainment by ${needed * 0.40:,.2f}/mo",
                "impact": "48-hour rule for non-essential purchases",
            },
        ]

    # ── formatting ─────────────────────────────────────────────────────

    @staticmethod
    def format_response(result: Dict[str, Any]) -> str:
        if "error" in result:
            return f"❌ {result['error']}"

        lines = [
            "═══ Savings Goal Plan ═══",
            "",
            f"🎯 Target: ${result['target_amount']:,.2f} by {result['deadline']}",
            f"📅 Time remaining: {result['months_remaining']} months",
            "",
            f"💰 Monthly savings needed: ${result['monthly_target']:,.2f}",
            f"📅 Weekly: ${result['weekly_target']:,.2f}",
            f"📆 Daily:   ${result['daily_target']:,.2f}",
        ]

        if result.get("on_track"):
            lines += ["", f"✅ You're on track! Monthly surplus: ${result['monthly_surplus']:,.2f}"]
        elif result.get("gap") is not None:
            lines += ["", f"📊 Monthly gap to close: ${result['gap']:,.2f}", "", "💡 How to close the gap:"]
            for s in result.get("cut_scenarios", []):
                lines.append(f"  • {s['action']}")
                lines.append(f"    ↳ {s['impact']}")

        return "\n".join(lines)
