#!/usr/bin/env python3
"""Regression tests: subscriptions vs bills vs habitual spending.

Real bug this guards against: _detect_recurring flagged any merchant
appearing >= 2 times at a similar amount as a "subscription". Rent
(2 x $1,200), utilities and internet all matched, so:

    Recurring Subscriptions: 9 items, TOTAL $1,493.51/mo, ANNUAL $17,922.12/yr
      - Rent Payment  $1,200.00/mo   <-- housing is not a subscription

That overstated the subscription total by ~$1,398/mo and produced the
absurd advice "you have 9 forgotten subscriptions — cancel them" about
someone's rent. The correct split on samples/sample_bank.csv is:

    subscriptions : Planet Fitness, Adobe, Netflix, Spotify  = $95.96/mo
    fixed bills   : Rent, Electric, Comcast, Water           = $1,392.40/mo
    habitual      : Starbucks (dining, recurs but neither)   -> excluded from both

Run:  .venv/bin/python tests/test_subscriptions.py
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

asyncio.set_event_loop(asyncio.new_event_loop())

from core.analyzer import Analyzer, is_subscription, is_bill  # noqa: E402
from core.categorizer import Categorizer  # noqa: E402
from core.parser import parse_any  # noqa: E402

PASSED = 0
FAILED = 0
SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "samples" / "sample_bank.csv"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


def _classify(merchant: str, category: str) -> str:
    item = {"merchant": merchant, "category": category, "amount": 10.0}
    if is_subscription(item):
        return "subscription"
    if is_bill(item):
        return "bill"
    return "habitual"


def main() -> int:
    print("=" * 60)
    print("  SUBSCRIPTIONS vs BILLS vs HABITUAL")
    print("=" * 60)

    # ── 1. classification of individual merchants ─────────────────────
    print("\n[1] Merchant classification")
    cases = [
        ("Netflix Subscription", "entertainment", "subscription"),
        ("Spotify Premium", "entertainment", "subscription"),
        ("Adobe Creative Cloud", "entertainment", "subscription"),
        ("Planet Fitness Gym", "health", "subscription"),
        # Bills: recurring obligations, never cancellable subscriptions.
        ("Rent Payment - Oakwood Apartments", "rent", "bill"),
        ("Electric Company Bill", "utilities", "bill"),
        ("Water Department", "utilities", "bill"),
        ("Comcast Internet", "utilities", "bill"),
        ("State Farm Insurance", "insurance", "bill"),
        # Habitual: recurs, but neither a subscription nor a fixed bill.
        ("Starbucks Coffee", "dining", "habitual"),
        ("Chipotle Mexican Grill", "dining", "habitual"),
    ]
    for merchant, category, expected in cases:
        got = _classify(merchant, category)
        check(f"{merchant[:34]:<34} → {expected}", got == expected, f"got {got}")

    # ── 2. the sample CSV produces an honest split ────────────────────
    print("\n[2] samples/sample_bank.csv split")
    txns = parse_any(SAMPLE.read_text())
    Categorizer().categorize_all(txns)
    result = Analyzer().analyze(txns)

    subs = [s for s in result.recurring_items if is_subscription(s)]
    bills = [s for s in result.recurring_items if is_bill(s)]
    sub_names = sorted(s["merchant"].lower() for s in subs)

    check("4 subscriptions found", len(subs) == 4, f"got {len(subs)}: {sub_names}")
    check(
        "subscriptions are the streaming/software/gym set",
        sub_names == ["adobe", "netflix", "planet fitness", "spotify"],
        f"got {sub_names}",
    )
    check("no rent in subscriptions", not any("rent" in n for n in sub_names))

    sub_total = sum(s["amount"] for s in subs)
    check(
        "subscription total is $95.96/mo",
        abs(sub_total - 95.96) < 0.01,
        f"got ${sub_total:,.2f}",
    )

    bill_names = sorted(b["merchant"].lower() for b in bills)
    check("rent is classified as a bill", any("rent" in n for n in bill_names))
    check("utilities are bills", any("electric" in n for n in bill_names))

    bill_total = sum(b["amount"] for b in bills)
    check(
        "bill total is $1,392.40/mo",
        abs(bill_total - 1392.40) < 0.01,
        f"got ${bill_total:,.2f}",
    )

    # The old bug: rent inflated the subscription total 15x.
    check(
        "subscription total is nowhere near the old $1,493.51",
        sub_total < 500,
        f"got ${sub_total:,.2f}",
    )

    # ── 3. habitual spending is in neither bucket ─────────────────────
    print("\n[3] Habitual spending excluded from both totals")
    habitual = [
        s for s in result.recurring_items
        if not is_subscription(s) and not is_bill(s)
    ]
    check(
        "Starbucks is habitual, not a bill",
        any("starbucks" in s["merchant"].lower() for s in habitual),
        f"habitual: {[s['merchant'] for s in habitual]}",
    )
    check(
        "coffee is not counted in the bill total",
        not any("starbucks" in b["merchant"].lower() for b in bills),
    )

    # ── 4. every item is labelled exactly once ────────────────────────
    print("\n[4] Every recurring item carries a single 'kind'")
    for item in result.recurring_items:
        kind = item.get("kind")
        check(
            f"{item['merchant'][:28]:<28} kind={kind}",
            kind in ("subscription", "bill", "habitual"),
            f"got {kind!r}",
        )

    # ── 5. insight text does not call rent a subscription ─────────────
    print("\n[5] Insights never call rent a subscription")
    sub_insights = [i for i in result.insights if "subscription" in i.lower()]
    check("a subscription insight exists", bool(sub_insights))
    for line in sub_insights:
        check(
            "insight omits rent",
            "rent" not in line.lower(),
            f"leaked: {line[:70]}",
        )
    # The count-bearing insight must report the honest total; the follow-up
    # "cancel them" warning repeats only the count.
    total_lines = [i for i in sub_insights if "$" in i]
    check("a dollar total is reported", bool(total_lines))
    for line in total_lines:
        check(
            "total is the honest $95.96",
            "95.96" in line,
            f"got: {line[:70]}",
        )

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
