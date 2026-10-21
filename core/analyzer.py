"""Financial analytics: totals, savings rate, fixed-vs-variable,
needs-vs-wants, recurring detection, deterministic insights."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

from .models import Transaction

# ──────────────────────── category groupings ───────────────────────────

FIXED_CATEGORIES = {"rent", "utilities", "subscriptions", "insurance", "education"}
NEED_CATEGORIES = {"groceries", "rent", "utilities", "transport", "health"}
WANT_CATEGORIES = {"dining", "entertainment", "shopping"}

# Merchants we *know* are subscription services (single-month detection)
KNOWN_SUBSCRIPTION_MERCHANTS = {
    "netflix", "spotify", "hulu", "disney+", "hbo", "hbo max",
    "adobe", "adobe creative cloud", "microsoft 365", "office 365",
    "amazon prime", "apple music", "youtube premium", "youtube music",
    "dropbox", "google one", "icloud", "github pro", "figma",
    "patreon", "planet fitness", "la fitness", "classpass", "peloton",
    "audible", "paramount+", "peacock",
}

# ─────────────────── what counts as a "subscription" ───────────────────

# Categories whose recurring charges are FIXED BILLS, not subscriptions.
# Rent and utilities repeat monthly at a stable amount, so a naive
# "same merchant, similar amount, >= 2 times" rule flags them as
# subscriptions. Reporting rent as a $1,200/mo "subscription" badly
# overstates the total (and the "cancel unused subscriptions" advice is
# nonsense for housing). These are tracked as recurring BILLS instead.
BILL_CATEGORIES = {"rent", "utilities", "insurance", "education", "loans", "taxes"}

# Keywords marking merchants that are bills/obligations rather than
# discretionary subscriptions, regardless of how they're categorised.
BILL_MERCHANT_KEYWORDS = {
    "rent", "mortgage", "lease", "landlord", "apartment",
    "electric", "water", "gas bill", "utility", "internet", "broadband",
    "comcast", "xfinity", "verizon fios", "spectrum", "at&t", "t-mobile",
    "phone bill", "insurance", "premium insurance", "tuition",
    "student loan", "car loan", "loan payment", "property tax",
}


def is_subscription(item: Dict) -> bool:
    """True only for discretionary subscriptions (streaming, software, gym).

    A recurring CHARGE is not automatically a subscription: rent and
    utilities recur too. Real-world budgets put them in separate buckets,
    and "you have N forgotten subscriptions — cancel them" must never
    refer to someone's housing.
    """
    merchant = str(item.get("merchant", "")).lower()

    if item.get("category") in BILL_CATEGORIES:
        return False
    if any(kw in merchant for kw in BILL_MERCHANT_KEYWORDS):
        return False

    return item.get("category") in ("subscriptions", "entertainment", "health") or any(
        kw in merchant for kw in KNOWN_SUBSCRIPTION_MERCHANTS
    )


def is_bill(item: Dict) -> bool:
    """True for recurring FIXED BILLS: rent, utilities, insurance, phone.

    Deliberately narrower than "everything that isn't a subscription".
    A daily coffee habit recurs at a stable amount, but it is neither a
    subscription nor a fixed bill — lumping it in with rent would make the
    fixed-bill total meaningless.
    """
    merchant = str(item.get("merchant", "")).lower()

    if item.get("category") in BILL_CATEGORIES:
        return True
    return any(kw in merchant for kw in BILL_MERCHANT_KEYWORDS)


# ──────────────────────── result container ────────────────────────────


@dataclass
class AnalysisResult:
    total_income: float = 0.0
    total_expenses: float = 0.0
    net: float = 0.0
    savings_rate: float = 0.0
    category_totals: Dict[str, float] = field(default_factory=dict)
    fixed_expenses: float = 0.0
    variable_expenses: float = 0.0
    needs: float = 0.0
    wants: float = 0.0
    recurring_items: List[Dict] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    top_categories: List[Tuple[str, float]] = field(default_factory=list)
    txn_count: int = 0


# ──────────────────────── analyzer ────────────────────────────────────


class Analyzer:
    def analyze(self, transactions: List[Transaction]) -> AnalysisResult:
        r = AnalysisResult()
        r.txn_count = len(transactions)

        if not transactions:
            r.insights.append(
                "No transactions to analyse. Paste your spending data to get started!"
            )
            return r

        # ── totals ──
        for t in transactions:
            if t.amount > 0:
                r.total_income += t.amount
            else:
                r.total_expenses += abs(t.amount)

        r.net = r.total_income - r.total_expenses
        r.savings_rate = (r.net / r.total_income * 100) if r.total_income > 0 else 0.0

        # ── per-category (expenses only) ──
        for t in transactions:
            if t.amount < 0:
                cat = t.category
                r.category_totals[cat] = r.category_totals.get(cat, 0.0) + abs(t.amount)

        # ── fixed vs variable ──
        for cat, total in r.category_totals.items():
            if cat in FIXED_CATEGORIES:
                r.fixed_expenses += total
            else:
                r.variable_expenses += total

        # ── needs vs wants ──
        for cat, total in r.category_totals.items():
            if cat in NEED_CATEGORIES:
                r.needs += total
            elif cat in WANT_CATEGORIES:
                r.wants += total

        # ── top categories ──
        r.top_categories = sorted(
            r.category_totals.items(), key=lambda x: x[1], reverse=True
        )

        # ── recurring detection ──
        r.recurring_items = self._detect_recurring(transactions)

        # ── insights ──
        r.insights = self._generate_insights(r)

        return r

    # ──────────────────── recurring detection ────────────────────────

    def _detect_recurring(self, transactions: List[Transaction]) -> List[Dict]:
        merchant_txns: Dict[str, List[Transaction]] = defaultdict(list)
        for t in transactions:
            if t.amount < 0 and t.merchant:
                merchant_txns[t.merchant.lower()].append(t)

        recurring: List[Dict] = []

        for key, txns in merchant_txns.items():
            # Frequency-based (≥ 2 occurrences, similar amounts)
            if len(txns) >= 2:
                amounts = [abs(t.amount) for t in txns]
                avg = sum(amounts) / len(amounts)
                similar = all(abs(a - avg) <= avg * 0.10 for a in amounts)
                if similar:
                    recurring.append(
                        {
                            "merchant": txns[0].merchant,
                            "amount": round(avg, 2),
                            "frequency": "monthly",
                            "occurrences": len(txns),
                            "category": txns[0].category,
                        }
                    )
                    continue

            # Known-subscription heuristic (single occurrence is enough)
            if any(kw in key for kw in KNOWN_SUBSCRIPTION_MERCHANTS):
                recurring.append(
                    {
                        "merchant": txns[0].merchant,
                        "amount": round(abs(txns[0].amount), 2),
                        "frequency": "monthly",
                        "occurrences": len(txns),
                        "category": txns[0].category,
                    }
                )

        # De-duplicate by merchant (keep highest amount)
        seen: Dict[str, Dict] = {}
        for item in recurring:
            m = item["merchant"].lower()
            if m not in seen or item["amount"] > seen[m]["amount"]:
                seen[m] = item

        items = sorted(seen.values(), key=lambda x: x["amount"], reverse=True)

        # Label each charge so callers never have to guess. "subscription"
        # is discretionary (streaming, software, gym); "bill" is a fixed
        # obligation (rent, utilities, insurance). Habitual spending that
        # merely repeats (e.g. a daily coffee) is neither — it's "habitual",
        # so it appears in neither the subscription nor the bill total.
        for item in items:
            if is_subscription(item):
                item["kind"] = "subscription"
            elif is_bill(item):
                item["kind"] = "bill"
            else:
                item["kind"] = "habitual"

        return items

    # ──────────────────── insight generation ─────────────────────────

    def _generate_insights(self, r: AnalysisResult) -> List[str]:
        insights: List[str] = []

        # Savings rate
        if r.savings_rate < 0:
            insights.append(
                f"⚠️  You're spending more than you earn! Net: ${r.net:,.2f}. Time to cut back."
            )
        elif r.savings_rate < 10:
            insights.append(
                f"💡 Savings rate is {r.savings_rate:.1f}%. Aim for at least 20% of income."
            )
        elif r.savings_rate < 20:
            insights.append(
                f"👍 Savings rate: {r.savings_rate:.1f}%. Getting close to the 20% target!"
            )
        else:
            insights.append(
                f"🎉 Great savings rate: {r.savings_rate:.1f}%! Keep it up!"
            )

        # Biggest category
        if r.top_categories:
            top_cat, top_amt = r.top_categories[0]
            if top_cat != "income" and r.total_expenses > 0:
                pct = top_amt / r.total_expenses * 100
                insights.append(
                    f"📊 Your biggest expense: '{top_cat}' at ${top_amt:,.2f} ({pct:.0f}% of spending)."
                )

        # Subscriptions — discretionary only. is_subscription() excludes
        # rent/utilities, which also recur but are not subscriptions.
        subs = [s for s in r.recurring_items if is_subscription(s)]
        if subs:
            total_sub = sum(s["amount"] for s in subs)
            names = [s["merchant"] for s in subs]
            insights.append(
                f"🔁 Found {len(subs)} recurring subscription(s): {', '.join(names)}. "
                f"Total: ${total_sub:,.2f}/mo."
            )
            if len(subs) >= 3:
                insights.append(
                    f"⚠️  You have {len(subs)} forgotten subscriptions! "
                    "Consider cancelling ones you don't use."
                )

        # Wants ratio
        if r.total_expenses > 0:
            wants_pct = r.wants / r.total_expenses * 100
            if wants_pct > 30:
                insights.append(
                    f"🛍️  {wants_pct:.0f}% of your spending is on wants. "
                    "Try to keep this under 30%."
                )

        return insights

    # ──────────────────── report formatting ──────────────────────────

    def get_report(self, r: AnalysisResult) -> str:
        lines = [
            "═══ Financial Health Report ═══",
            "",
            f"💰 Income:    ${r.total_income:>10,.2f}",
            f"💸 Expenses:  ${r.total_expenses:>10,.2f}",
            f"📈 Net:       ${r.net:>10,.2f}",
            f"📊 Savings:   {r.savings_rate:>10.1f}%",
            "",
        ]

        if r.category_totals:
            lines.append("── Spending by Category ──")
            for cat, total in r.top_categories:
                if cat != "income":
                    lines.append(f"  {cat:<15} ${total:>10,.2f}")
            lines.append("")

        if r.insights:
            lines.append("── Insights ──")
            for ins in r.insights:
                lines.append(f"  {ins}")

        return "\n".join(lines)
