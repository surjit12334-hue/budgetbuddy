"""Interactive-card builders (7 cards).  Disabled by default;
markdown fallback always works."""

import os
from typing import Dict, Any, List

from .analyzer import AnalysisResult


class CardBuilder:
    def __init__(self):
        self.enabled = os.environ.get("ENABLE_CARDS", "false").lower() == "true"

    # ── envelope ───────────────────────────────────────────────────────

    @staticmethod
    def _wrap(card_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"type": card_type, "version": "1.0", "data": data}

    # ── 1. onboarding form ─────────────────────────────────────────────

    def build_onboarding_form(self) -> Dict:
        return self._wrap(
            "form",
            {
                "title": "Welcome to BudgetBuddy! 🎉",
                "description": "Let's set up your financial profile.",
                "fields": [
                    {"name": "monthly_income", "type": "number",
                     "label": "Monthly Income ($)", "required": True},
                    {"name": "savings_goal", "type": "number",
                     "label": "Monthly Savings Goal ($)", "required": False},
                ],
            },
        )

    # ── 2. dashboard ───────────────────────────────────────────────────

    def build_dashboard(self, analysis: AnalysisResult) -> Dict:
        return self._wrap(
            "dashboard",
            {
                "title": "Financial Dashboard",
                "metrics": {
                    "income": analysis.total_income,
                    "expenses": analysis.total_expenses,
                    "net": analysis.net,
                    "savings_rate": analysis.savings_rate,
                },
                "categories": [
                    {"name": c, "amount": a}
                    for c, a in analysis.top_categories[:5]
                    if c != "income"
                ],
            },
        )

    # ── 3. insights carousel ───────────────────────────────────────────

    def build_insights_carousel(self, insights: List[str]) -> Dict:
        return self._wrap(
            "carousel",
            {
                "title": "Your Insights",
                "items": [{"text": ins, "icon": "💡"} for ins in insights],
            },
        )

    # ── 4. goal card ───────────────────────────────────────────────────

    def build_goal_card(self, goal_data: Dict) -> Dict:
        return self._wrap(
            "card",
            {
                "title": f"Savings Goal: ${goal_data.get('target_amount', 0):,.0f}",
                "progress": {
                    "target": goal_data.get("target_amount", 0),
                    "deadline": goal_data.get("deadline", ""),
                    "monthly_needed": goal_data.get("monthly_target", 0),
                },
                "on_track": goal_data.get("on_track", False),
            },
        )

    # ── 5. split card ──────────────────────────────────────────────────

    def build_split_card(self, description: str, total: float,
                         shares: List[Dict]) -> Dict:
        return self._wrap(
            "card",
            {"title": f"Split: {description}", "total": total, "shares": shares},
        )

    # ── 6. checkout card ───────────────────────────────────────────────

    def build_checkout_card(self, request_id: str, amount: float,
                            description: str) -> Dict:
        return self._wrap(
            "checkout",
            {
                "title": "Upgrade to Pro",
                "description": description,
                "amount": amount,
                "currency": "USD",
                "request_id": request_id,
            },
        )

    # ── 7. report card ─────────────────────────────────────────────────

    def build_report_card(self, analysis: AnalysisResult) -> Dict:
        return self._wrap(
            "card",
            {
                "title": "Monthly Report",
                "summary": {
                    "income": analysis.total_income,
                    "expenses": analysis.total_expenses,
                    "savings_rate": analysis.savings_rate,
                },
                "insights": analysis.insights[:3],
            },
        )
