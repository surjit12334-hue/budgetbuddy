"""ASI:One interactive-card builders.

Schema source (authoritative):
    https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards

Cards are declared inside a normal Agent Chat Protocol message: one
``TextContent`` bubble for narration plus exactly one ``MetadataContent``
block holding the card declaration.  ASI:One renders a drawer; when the
user acts, it sends the selection back as a ``TextContent`` message.

Wire format (metadata keys, all values MUST be strings)::

    card_protocol_version: "1"          <- omitting this silently drops the card
    requires_card_interaction: "true"
    card_kind: "carousel"|"detail"|"form"|"review"|"custom"
    card_payload: json.dumps(payload)   <- payload at the TOP level, no wrapper

Two rules that are easy to get wrong, both called out in the docs:

* ``card_payload`` must be the payload itself, never ``{"data": {...}}``.
* ``MetadataContent.metadata`` is ``dict[str, str]`` — JSON-encode nested
  structures (hence ``json.dumps`` for the payload).

Validation failures degrade silently to plain text, so a broken card is
never a hard failure: the user still reads the narration.  That is also
why every builder here returns a plain dict that ``as_metadata`` can
JSON-encode, and why the markdown fallback in the orchestrator stays the
source of truth when ``ENABLE_CARDS=false``.

Four predefined kinds: ``carousel``, ``detail``, ``form``, ``review``.
Everything else is ``card_kind: "custom"`` — an element tree rooted at
``{"root": <element>}``, nesting capped at 8 levels.
"""

import json
import os
from typing import Any, Dict, List, Optional

from .analyzer import AnalysisResult, is_subscription

CARD_PROTOCOL_VERSION = "1"

# ASI:One rejects payloads above 64 KB, and rejects unknown card_kinds.
MAX_PAYLOAD_BYTES = 64 * 1024
VALID_KINDS = {"carousel", "detail", "form", "review", "custom"}


class CardBuilder:
    """Builds ASI:One card payloads; disabled by default."""

    def __init__(self) -> None:
        self.enabled = os.environ.get("ENABLE_CARDS", "false").lower() == "true"

    # ── wire envelope ──────────────────────────────────────────────────

    def as_metadata(
        self,
        card_kind: str,
        payload: Dict[str, Any],
        *,
        is_terminal: bool = False,
        drawer_width_px: Optional[int] = None,
    ) -> Dict[str, str]:
        """Wrap a payload as the ``metadata`` dict for a ``MetadataContent``.

        Returns an empty dict when cards are disabled, so callers can simply
        do ``if meta:`` — the markdown reply is sent either way.
        """
        if not self.enabled:
            return {}
        if card_kind not in VALID_KINDS:
            raise ValueError(f"unknown card_kind: {card_kind!r}")

        encoded = json.dumps(payload)
        # Fail loudly here rather than have ASI:One silently drop the card.
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"card_payload exceeds {MAX_PAYLOAD_BYTES} bytes "
                f"({len(encoded.encode('utf-8'))})"
            )

        meta: Dict[str, str] = {
            "card_protocol_version": CARD_PROTOCOL_VERSION,
            "requires_card_interaction": "false" if is_terminal else "true",
            "card_kind": card_kind,
            "card_payload": encoded,
        }
        if drawer_width_px is not None:
            # ASI:One clamps to [320, 800]; clamp here so we send something sane.
            clamped = max(320, min(800, int(drawer_width_px)))
            meta["preferred_drawer_width_px"] = str(clamped)
        if is_terminal:
            meta["is_terminal"] = "true"
        return meta

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(amount: float) -> str:
        return f"${amount:,.2f}"

    # ── 1. onboarding form (card_kind: form) ───────────────────────────

    def build_onboarding_form(self) -> Dict[str, Any]:
        return {
            "title": "Welcome to BudgetBuddy! 🎉",
            "fields": [
                {
                    "name": "monthly_income",
                    "kind": "number",
                    "label": "Monthly income ($)",
                    "required": True,
                },
                {
                    "name": "savings_goal",
                    "kind": "number",
                    "label": "Monthly savings goal ($)",
                    "required": False,
                },
                {
                    "name": "currency",
                    "kind": "select",
                    "label": "Currency",
                    "options": [
                        {"value": "USD", "label": "US Dollar"},
                        {"value": "GBP", "label": "Pound Sterling"},
                        {"value": "EUR", "label": "Euro"},
                    ],
                },
            ],
            "submit_cta": {
                "label": "Set up my profile",
                "selection": {"action": "onboarding_submit"},
            },
        }

    # ── 2. dashboard (card_kind: custom) ──────────────────────────────

    def build_dashboard(self, analysis: AnalysisResult) -> Dict[str, Any]:
        """Health report as an element tree — no predefined kind fits."""
        rows: List[Dict[str, Any]] = [
            {
                "type": "group",
                "direction": "row",
                "gap": 16,
                "children": [
                    {"type": "text", "value": "Income", "style": "muted"},
                    {
                        "type": "text",
                        "value": self._fmt(analysis.total_income),
                        "style": "emphasis",
                    },
                ],
            },
            {
                "type": "group",
                "direction": "row",
                "gap": 16,
                "children": [
                    {"type": "text", "value": "Expenses", "style": "muted"},
                    {"type": "text", "value": self._fmt(analysis.total_expenses)},
                ],
            },
            {"type": "divider"},
            {
                "type": "group",
                "direction": "row",
                "gap": 16,
                "children": [
                    {"type": "text", "value": "Net saved", "style": "muted"},
                    {
                        "type": "text",
                        "value": self._fmt(analysis.net),
                        "style": "emphasis",
                    },
                ],
            },
            {
                "type": "group",
                "direction": "row",
                "gap": 16,
                "children": [
                    {"type": "text", "value": "Savings rate", "style": "muted"},
                    {"type": "text", "value": f"{analysis.savings_rate:.1f}%"},
                ],
            },
        ]

        top = [(c, a) for c, a in analysis.top_categories if c != "income"][:5]
        if top:
            rows.append({"type": "divider"})
            rows.append({"type": "heading", "value": "Top categories", "level": 3})
            for cat, amount in top:
                rows.append(
                    {
                        "type": "group",
                        "direction": "row",
                        "gap": 16,
                        "children": [
                            {"type": "text", "value": cat.title(), "style": "muted"},
                            {"type": "text", "value": self._fmt(amount)},
                        ],
                    }
                )

        return {
            "root": {
                "type": "section",
                "title": "Your financial dashboard",
                "children": rows,
            }
        }

    # ── 3. insights carousel (card_kind: carousel) ────────────────────

    def build_insights_carousel(self, insights: List[str]) -> Dict[str, Any]:
        items = []
        for i, insight in enumerate(insights):
            # "⚠️  You have 4 forgotten..." → title/body split for readability.
            text = insight.strip()
            items.append(
                {
                    "id": f"insight_{i}",
                    "title": text[:60] + ("…" if len(text) > 60 else ""),
                    "subtitle": text,
                    "primary_cta": {
                        "label": "Got it",
                        "selection": {"action": "dismiss_insight", "insight_id": f"insight_{i}"},
                    },
                }
            )
        return {"title": "Your insights", "items": items}

    # ── 4. goal plan (card_kind: custom) ──────────────────────────────

    def build_goal_card(self, goal_data: Dict[str, Any]) -> Dict[str, Any]:
        target = goal_data.get("target_amount", 0) or 0
        monthly = goal_data.get("monthly_target", 0) or 0
        on_track = bool(goal_data.get("on_track", False))

        rows: List[Dict[str, Any]] = [
            {
                "type": "group",
                "direction": "row",
                "gap": 16,
                "children": [
                    {"type": "text", "value": "Target", "style": "muted"},
                    {"type": "text", "value": self._fmt(target), "style": "emphasis"},
                ],
            },
            {
                "type": "group",
                "direction": "row",
                "gap": 16,
                "children": [
                    {"type": "text", "value": "Deadline", "style": "muted"},
                    {"type": "text", "value": str(goal_data.get("deadline", "—"))},
                ],
            },
            {"type": "divider"},
            {
                "type": "group",
                "direction": "row",
                "gap": 16,
                "children": [
                    {"type": "text", "value": "Monthly needed", "style": "muted"},
                    {
                        "type": "text",
                        "value": self._fmt(monthly),
                        "style": "emphasis",
                    },
                ],
            },
            {
                "type": "badge",
                "label": "On track" if on_track else "Needs attention",
                "variant": "success" if on_track else "warning",
            },
        ]

        return {
            "root": {
                "type": "section",
                "title": "🎯 Savings goal plan",
                "children": rows,
            }
        }

    # ── 5. bill split (card_kind: custom, list) ───────────────────────

    def build_split_card(
        self, description: str, total: float, shares: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        items = []
        for share in shares:
            name = share.get("name", "?")
            amount = share.get("amount", 0)
            items.append(
                {
                    "children": [
                        {"type": "heading", "value": str(name), "level": 3},
                        {"type": "text", "value": self._fmt(amount)},
                    ],
                    "action": {
                        "selection": {"action": "settle_share", "person": name, "amount": amount}
                    },
                }
            )

        return {
            "root": {
                "type": "section",
                "title": f"Split: {description}",
                "subtitle": f"Total {self._fmt(total)}",
                "children": [
                    {"type": "list", "items": items},
                    {"type": "divider"},
                    {
                        "type": "button",
                        "label": "Remind everyone",
                        "primary": True,
                        "action": {"selection": {"action": "remind_all"}},
                    },
                ],
            }
        }

    # ── 6. Pro checkout (card_kind: review) ───────────────────────────

    def build_checkout_card(
        self, request_id: str, amount: float, description: str
    ) -> Dict[str, Any]:
        return {
            "title": "Upgrade to BudgetBuddy Pro",
            "summary_rows": [
                {"label": "Product", "value": description},
                {"label": "Price", "value": self._fmt(amount)},
                {"label": "Billing", "value": "One-time · lifetime access"},
                {"label": "Request ID", "value": request_id},
            ],
            "approve_cta": {
                "label": "Confirm payment",
                "primary": True,
                "selection": {"action": "confirm_payment", "request_id": request_id},
            },
            "reject_cta": {
                "label": "Not now",
                "selection": {"action": "cancel_payment", "request_id": request_id},
            },
        }

    # ── 7. subscriptions (card_kind: carousel) ────────────────────────

    def build_subscriptions_card(self, analysis: AnalysisResult) -> Dict[str, Any]:
        subs = [s for s in analysis.recurring_items if is_subscription(s)]
        items = [
            {
                "id": f"sub_{i}",
                "title": s["merchant"],
                "subtitle": f"{self._fmt(s['amount'])}/mo · {s['category']}",
                "secondary_text": f"{self._fmt(s['amount'] * 12)}/yr",
                "primary_cta": {
                    "label": "Review",
                    "selection": {
                        "action": "review_subscription",
                        "merchant": s["merchant"],
                    },
                },
            }
            for i, s in enumerate(subs)
        ]
        total = sum(s["amount"] for s in subs)
        return {
            "title": "Your subscriptions",
            "subtitle": f"{len(subs)} active · {self._fmt(total)}/mo",
            "items": items,
        }
