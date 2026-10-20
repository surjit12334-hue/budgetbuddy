#!/usr/bin/env python3
"""Phase 3.2 — adversarial parser tests.

Throws hostile input at the pipeline and asserts that every case
produces a helpful message and NEVER a traceback.

Run:  .venv/bin/python tests/test_adversarial.py
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.orchestrator import Orchestrator
from core.parser import parse_any, parse_csv, parse_freetext, parse_date, parse_amount

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}  {detail}")


def sa_fe(label, text, expect_ingest=True):
    """Run text through the orchestrator; assert no exception + sane reply.

    expect_ingest=True  → reply must be an ingest result OR a graceful
                          "couldn't find transactions" message.
    expect_ingest=False → any non-empty string reply is acceptable.
    """
    global PASS, FAIL
    orch = Orchestrator()
    sid = f"adv-{label}"
    try:
        reply = orch.handle(sid, text)
    except Exception as exc:
        FAIL += 1
        print(f"  ❌ {label}: RAISED {type(exc).__name__}: {exc}")
        return
    if not isinstance(reply, str) or not reply.strip():
        FAIL += 1
        print(f"  ❌ {label}: empty/non-string reply")
        return
    if expect_ingest:
        ok = ("Parsed" in reply) or ("couldn't find" in reply)
    else:
        ok = True
    if ok:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}: unexpected reply: {reply[:70]!r}")


def never_crashes(label, text):
    """Assert the orchestrator returns a non-empty string and never raises."""
    global PASS, FAIL
    orch = Orchestrator()
    try:
        reply = orch.handle(f"hard-{label}", text)
    except Exception as exc:
        FAIL += 1
        print(f"  ❌ {label}: RAISED {type(exc).__name__}: {exc}")
        return
    if isinstance(reply, str) and reply.strip():
        PASS += 1
        print(f"  ✅ {label} (graceful reply)")
    else:
        FAIL += 1
        print(f"  ❌ {label}: empty reply")


print("=" * 64)
print("PHASE 3.2 ADVERSARIAL TESTS")
print("=" * 64)

# ── A. messy but parseable CSVs ────────────────────────────────────────
print("\n[A] Messy-but-valid CSVs (should parse)")
sa_fe("no headers", "01/15/2024,Starbucks Coffee,-5.45\n01/16/2024,Netflix,-15.99\n01/17/2024,Shell Gas,-42.00")
sa_fe("semicolon delimiter", "Date;Description;Amount\n15/01/2024;Cafe Nero;-3.50\n16/01/2024;Tesco;-22.10")
sa_fe("tab delimiter", "Date\tDescription\tAmount\n2024-01-15\tUber\t-18.40\n2024-01-16\tLyft\t-9.99")
sa_fe("pipe delimiter", "Date|Description|Amount\n2024-01-15|Uber|-18.40")
sa_fe("euro symbol", "Date,Description,Amount\n15/01/2024,Cafe,-€12.50\n16/01/2024,Supermarket,-€45.00")
sa_fe("pound symbol", "Date,Description,Amount\n15/01/2024,Tesco,-£22.10")
sa_fe("rupee symbol", "Date,Description,Amount\n15/01/2024,Swiggy,-₹450.00\n16/01/2024,Zomato,-₹380.00")
sa_fe("parenthesized negatives", "Date,Description,Amount\n01/15/2024,Coffee,(5.45)\n01/16/2024,Refund,25.00")
sa_fe("debit/credit columns", "Date,Description,Debit,Credit\n01/15/2024,Salary,,3500.00\n01/16/2024,Rent,1200.00,")
sa_fe("ambiguous dates", "Date,Description,Amount\n01/02/2024,Ambiguous A,-10.00\n03/04/2024,Ambiguous B,-20.00")
sa_fe("thousands separators", "Date,Description,Amount\n2024-01-15,Purchase,\"-1,234.56\"")

# ── B. hostile / garbage ───────────────────────────────────────────────
print("\n[B] Hostile input (must NOT crash)")
sa_fe("empty string", "", expect_ingest=False)
sa_fe("whitespace only", "   \n  \n\t\n   ", expect_ingest=False)
sa_fe("garbage text", "asdfghjkl qwerty zxcvbnm !@#$%^&*()", expect_ingest=False)
sa_fe("only a header", "Date,Description,Amount", expect_ingest=False)
sa_fe("numbers not money", "1 2 3 4 5 6 7 8 9", expect_ingest=False)
sa_fe("emoji soup", "🎉🎉🎉 💸💸🔥🔥", expect_ingest=False)
sa_fe("huge single number", "Date,Description,Amount\n2024-01-15,Weird,999999999999999999999999.99")
sa_fe("negative-looking junk", "Date,Description,Amount\n2024-01-15,Bad,--12..34", expect_ingest=False)
sa_fe("mixed delimiters", "a,b;c|d\te\n1,2;3|4\t5", expect_ingest=False)
sa_fe("null bytes", "Date,Description,Amount\n2024-01-15,Null\x00Byte,-5.00")
sa_fe("very long line", "Date,Description,Amount\n2024-01-15," + "X" * 5000 + ",-5.00")
sa_fe("unicode chaos", "日期,描述,金额\n2024-01-15,カフェ,-500", expect_ingest=False)
sa_fe("markdown table", "| Date | Description | Amount |\n|---|---|---|\n| 2024-01-15 | Coffee | -5.00 |")

# ── C. 500-row stress file ─────────────────────────────────────────────
print("\n[C] Stress: 500-row file")
rows = ["Date,Description,Amount"]
for i in range(500):
    d = f"{1 + i % 28:02d}/{1 + i % 12:02d}/2024"
    rows.append(f"{d},Merchant {i},-{10 + (i % 90)}.{i % 100:02d}")
big = "\n".join(rows)
sa_fe("500 rows parse", big)
orch = Orchestrator()
r = orch.handle("stress", big)
check("500-row count correct", "Parsed 500" in r, f"got: {r[:60]}")

# ── D. type-level edge cases ───────────────────────────────────────────
print("\n[D] Direct parser edge cases (no traceback)")
for label, fn, arg in [
    ("parse_date empty", parse_date, ""),
    ("parse_date junk", parse_date, "not-a-date"),
    ("parse_amount empty", parse_amount, ""),
    ("parse_amount junk", parse_amount, "abc"),
    ("parse_amount symbol only", parse_amount, "€"),
    ("parse_csv empty", parse_csv, ""),
    ("parse_freetext empty", parse_freetext, ""),
    ("parse_any empty", parse_any, ""),
]:
    try:
        fn(arg)
        PASS += 1
        print(f"  ✅ {label}")
    except Exception as exc:
        FAIL += 1
        print(f"  ❌ {label}: {type(exc).__name__}: {exc}")

# ── E. bad intents don't crash ─────────────────────────────────────────
print("\n[E] Malformed intents")
sa_fe("save with no amount", "I want to save money by August", expect_ingest=False)
sa_fe("split with no amount", "split the bill with Alice", expect_ingest=False)
sa_fe("split with no names", "split this $50", expect_ingest=False)
sa_fe("goal no deadline", "save $5000", expect_ingest=False)
sa_fe("subscriptions no data", "what subscriptions do I have?", expect_ingest=False)
sa_fe("analysis no data", "how am I doing?", expect_ingest=False)
sa_fe("random question", "what is the meaning of life?", expect_ingest=False)

# ── F. fuzz: random garbage must never crash ───────────────────────────
print("\n[F] Fuzz (random bytes / extreme inputs)")
import random
import string

random.seed(1234)
alphabet = string.printable + "€£₹¥áéíóú日本語🎉\x00\x01"
fuzz_fail = 0
for i in range(200):
    n = random.randint(0, 400)
    s = "".join(random.choice(alphabet) for _ in range(n))
    orch = Orchestrator()
    try:
        r = orch.handle(f"fuzz-{i}", s)
        if not (isinstance(r, str) and r.strip()):
            fuzz_fail += 1
    except Exception as exc:
        fuzz_fail += 1
        print(f"  ❌ fuzz #{i} raised {type(exc).__name__}: {exc}  input={s[:50]!r}")
        break
if fuzz_fail == 0:
    PASS += 1
    print("  ✅ 200 random inputs — zero crashes, all graceful replies")
else:
    FAIL += 1
    print(f"  ❌ {fuzz_fail} fuzz inputs failed")

# extreme sizes
never_crashes("10k comma line", "Date,Description,Amount\n" + "a," * 10000 + "b")
never_crashes("many newlines", "\n" * 5000)
never_crashes("deep unicode", "🏦" * 3000)

# ── summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 64)
sys.exit(0 if FAIL == 0 else 1)
