#!/usr/bin/env python3
"""Phase 1 smoke test — run from repo root:  python tests/smoke.py"""

import sys, os, pathlib

# Ensure core package is importable
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import Transaction, Goal
from core.state import SessionStore
from core.llm import LLMClient
from core.parser import parse_csv, parse_freetext, parse_any, parse_date, parse_amount
from core.categorizer import Categorizer, normalize_merchant
from core.analyzer import Analyzer
from core.coach import Coach
from core.goal import GoalCalculator
from core.splitter import SplitCalculator
from core.payments import PaymentManager
from core.cards import CardBuilder
from core.orchestrator import Orchestrator

PASS = 0
FAIL = 0

def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}  {detail}")


print("=" * 60)
print("PHASE 1 SMOKE TEST")
print("=" * 60)

# ── 1.1 state ──────────────────────────────────────────────────────────
print("\n[1.1] SessionStore")
db = ROOT / "test_sessions.db"
if db.exists():
    db.unlink()
store = SessionStore(db_path=str(db), ttl_hours=1)
s = store.create_session("test-1")
check("create_session returns dict", isinstance(s, dict))
store.save_transactions("test-1", [Transaction(date=__import__('datetime').datetime.now(), amount=-5.0, description="coffee")])
loaded = store.load_transactions("test-1")
check("save/load roundtrip", len(loaded) == 1 and loaded[0].description == "coffee")
check("get_or_create", store.get_or_create("new-sess") is not None)
db.unlink(missing_ok=True)

# ── 1.2 parser ─────────────────────────────────────────────────────────
print("\n[1.2] Parser")
csv_text = (ROOT / "samples" / "sample_bank.csv").read_text()
txns = parse_csv(csv_text)
check("sample CSV → 38 txns", len(txns) == 38, f"got {len(txns)}")

# Date format coverage
for s, fmt in [("01/15/2024","us slash"),("15/01/2024","eu slash"),("2024-01-15","iso"),
               ("15-01-2024","eu dash"),("Jan 15, 2024","mon d, yyyy"),("15 Jan 2024","d mon yyyy")]:
    dt, _ = parse_date(s)
    check(f"date format: {s} ({fmt})", dt is not None)

# Amount parsing
for raw, expected in [("$50.00", 50.0), ("(50.00)", -50.0), ("€30", 30.0),
                      ("₹1500", 1500.0), ("1,234.56", 1234.56), ("-42.00", -42.0)]:
    val, _ = parse_amount(raw)
    check(f"amount: {raw} → {expected}", val == expected, f"got {val}")

# Ambiguity flag
_, amb = parse_date("01/02/2024")
check("ambiguous date flagged", amb is True)
_, not_amb = parse_date("01/15/2024")
check("unambiguous date not flagged", not_amb is False)

# Free-text
ft = parse_freetext("spent $50 on groceries yesterday\ncoffee $4.50")
check("free-text → 2 txns", len(ft) == 2, f"got {len(ft)}")
check("free-text expense is negative", ft[0].amount < 0)

# ── 1.3 categorizer ────────────────────────────────────────────────────
print("\n[1.3] Categorizer")
cat = Categorizer()
cat.categorize_all(txns)
categories = {t.category for t in txns}
check("all txns have categories", all(t.category != "" for t in txns))
check("merchant normalised (Netflix)", any(t.merchant == "Netflix" for t in txns))
check("income detected", "income" in categories)
check("groceries detected", "groceries" in categories)

# ── 1.4 analyzer ───────────────────────────────────────────────────────
print("\n[1.4] Analyzer")
analyzer = Analyzer()
analysis = analyzer.analyze(txns)
check("income > 0", analysis.total_income > 0)
check("expenses > 0", analysis.total_expenses > 0)
check("savings rate computed", 0 <= analysis.savings_rate <= 100)
check("recurring items detected", len(analysis.recurring_items) >= 3,
      f"got {len(analysis.recurring_items)}")
sub_names = [r["merchant"].lower() for r in analysis.recurring_items]
check("Netflix in subscriptions", any("netflix" in n for n in sub_names))
check("Spotify in subscriptions", any("spotify" in n for n in sub_names))

# "forgotten subscriptions" insight
insight_text = " ".join(analysis.insights)
check("'forgotten subscriptions' insight", "forgotten subscription" in insight_text.lower(),
      f"insights: {analysis.insights}")

report = analyzer.get_report(analysis)
check("report is non-empty string", len(report) > 50)

# ── 1.5 LLM ────────────────────────────────────────────────────────────
print("\n[1.5] LLM fallback chain")
llm = LLMClient()
# Without key, should degrade gracefully
result = llm.generate("Say hello")
check("LLM returns None (no key)", result is None)
check("LLM available is bool", isinstance(llm.available, bool))

# ── 1.6 Coach ──────────────────────────────────────────────────────────
print("\n[1.6] Coach fallback")
coach = Coach(llm=None)  # force fallback
coach_msg = coach.get_insights(analysis)
check("coach returns non-empty string", len(coach_msg) > 20)
check("coach mentions savings", "savings" in coach_msg.lower())
check("coach mentions budget", "budget" in coach_msg.lower())

# ── 1.7 Goal ───────────────────────────────────────────────────────────
print("\n[1.7] Goal calculator")
from datetime import datetime
goal = Goal(target_amount=3000, deadline=datetime(2024, 8, 1))
# deadline is in the past for 2026 test — verify error handling
result = goal_calc_result = GoalCalculator().calculate(goal, 4000, 3000)
check("past deadline → error", "error" in result)
future = Goal(target_amount=5000, deadline=datetime(2026, 12, 1))
result2 = GoalCalculator().calculate(future, 2000, 1900)
check("monthly_target computed", result2.get("monthly_target", 0) > 0)
check("cut_scenarios present", "cut_scenarios" in result2, f"got keys: {list(result2)}")

# ── 1.8 Splitter ───────────────────────────────────────────────────────
print("\n[1.8] Splitter")
sc = SplitCalculator()
shares = sc.even_split(90, ["You", "Alice", "Bob"])
check("even split → 3 shares", len(shares) == 3)
check("shares sum to 90", abs(sum(s["amount"] for s in shares) - 90) < 0.01)

settlements = sc.minimize_settlements({"Alice": 12, "Bob": -12, "You": 0})
check("settlement minimised", len(settlements) == 1)
check("settlement direction", settlements[0]["from"] == "Bob" and settlements[0]["to"] == "Alice")

# ── 1.9 Payments ───────────────────────────────────────────────────────
print("\n[1.9] Payments")
pm = PaymentManager()
req = pm.create_pro_request()
check("request created", req.status == "pending")
check("mark_paid works", pm.mark_paid(req.id))
check("is_pro True after payment", pm.is_pro(req.id))

# ── 1.10 Cards ─────────────────────────────────────────────────────────
# Builders emit plain payload dicts; as_metadata() wraps them in the
# ASI:One wire envelope.  Schema conformance is covered in depth by
# tests/test_cards.py — here we only check the builders are wired up.
print("\n[1.10] Cards")
cb = CardBuilder()
import json
cards = [
    cb.build_onboarding_form(),
    cb.build_dashboard(analysis),
    cb.build_insights_carousel(analysis.insights),
    cb.build_goal_card({"target_amount": 3000, "deadline": "Aug 2027", "monthly_target": 500}),
    cb.build_split_card("Dinner", 90, shares),
    cb.build_checkout_card(req.id, 4.99, "Pro"),
    cb.build_subscriptions_card(analysis),
]
all_valid = all(isinstance(json.dumps(c), str) for c in cards)
check("all 7 cards emit valid JSON", all_valid)
check("cards disabled by default", cb.enabled is False)

# Disabled → no metadata block, so the markdown reply is the whole answer.
check("disabled cards yield no metadata",
      cb.as_metadata("form", cards[0]) == {})

# ── 1.11 Orchestrator ──────────────────────────────────────────────────
print("\n[1.11] Orchestrator — full 6-turn flow")
orch = Orchestrator()
sid = "demo-session"

r1 = orch.handle(sid, csv_text)
check("turn 1: ingest", "Parsed 38" in r1, f"got: {r1[:80]}")

r2 = orch.handle(sid, "How am I doing?")
check("turn 2: analysis", "Financial Health" in r2, f"got: {r2[:80]}")

r3 = orch.handle(sid, "What subscriptions do I have?")
check("turn 3: subscriptions", "Recurring Subscriptions" in r3, f"got: {r3[:80]}")

r4 = orch.handle(sid, "I want to save $3000 by August")
check("turn 4: goal", "Savings Goal" in r4, f"got: {r4[:80]}")

r5 = orch.handle(sid, "Split this $90 dinner with Alice and Bob")
check("turn 5: split", "Split" in r5 and "Alice" in r5, f"got: {r5[:80]}")

r6 = orch.handle(sid, "How do I unlock Pro?")
check("turn 6: payment", "Payment Request" in r6, f"got: {r6[:80]}")

# ── summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
