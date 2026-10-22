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

# ── G. the demo CSV through hostile paths ──────────────────────────────
# The suite above uses hand-written hostile input.  Section G takes the file
# a judge will actually see — samples/sample_bank.csv — and mangles it the way
# a real bank export gets mangled: CRLF, BOM, another delimiter, no header,
# reordered columns, EU number format, Dr/Cr suffixes, a truncated row.
# The money story must survive every one of them.

print("\n[G] samples/sample_bank.csv under hostile transformations")

import csv
import io
import subprocess
import datetime

from core.categorizer import Categorizer
from core.analyzer import Analyzer, is_subscription, is_bill

DEMO_PATH = ROOT / "samples" / "sample_bank.csv"
DEMO_TEXT = DEMO_PATH.read_text()
DEMO_ROWS = list(csv.reader(io.StringIO(DEMO_TEXT)))
DEMO_HEADER, DEMO_DATA = DEMO_ROWS[0], DEMO_ROWS[1:]
DEMO_N = len(DEMO_DATA)
DEMO_TOTAL = sum(float(r[2]) for r in DEMO_DATA)
DEMO_INCOME = sum(float(r[2]) for r in DEMO_DATA if float(r[2]) > 0)
DEMO_SPEND = -sum(float(r[2]) for r in DEMO_DATA if float(r[2]) < 0)


def render(rows, header=None, delim=","):
    """Build CSV text with correct quoting for the given delimiter."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator="\n")
    if header:
        w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def demo_check(label, text, expect_n=DEMO_N, expect_total=DEMO_TOTAL):
    """Parse a mangled demo CSV: right count, right total, no crash."""
    global PASS, FAIL
    try:
        txns = parse_any(text)
    except Exception as exc:
        FAIL += 1
        print(f"  ❌ {label}: RAISED {type(exc).__name__}: {exc}")
        return None
    total = sum(t.amount for t in txns)
    if len(txns) != expect_n:
        FAIL += 1
        print(f"  ❌ {label}: parsed {len(txns)} txns, expected {expect_n}")
        return txns
    if abs(total - expect_total) > 0.005:
        FAIL += 1
        print(f"  ❌ {label}: total ${total:,.2f}, expected ${expect_total:,.2f}")
        return txns
    PASS += 1
    print(f"  ✅ {label}")
    return txns


def demo_money_check(label, text, expect_n=DEMO_N):
    """Parse + categorise + analyse: the story must not change."""
    global PASS, FAIL
    try:
        txns = parse_any(text)
        if len(txns) != expect_n:
            FAIL += 1
            print(f"  ❌ {label}: parsed {len(txns)} txns, expected {expect_n}")
            return
        Categorizer().categorize_all(txns)
        result = Analyzer().analyze(txns)
    except Exception as exc:
        FAIL += 1
        print(f"  ❌ {label}: RAISED {type(exc).__name__}: {exc}")
        return
    subs = sum(s["amount"] for s in result.recurring_items if is_subscription(s))
    bills = sum(s["amount"] for s in result.recurring_items if is_bill(s))
    if abs(subs - 95.96) > 0.01 or abs(bills - 1392.40) > 0.01:
        FAIL += 1
        print(f"  ❌ {label}: subs ${subs:,.2f} / bills ${bills:,.2f}, "
              f"expected $95.96 / $1,392.40")
        return
    PASS += 1
    print(f"  ✅ {label}")


def demo_orch(label, text, expect_n=DEMO_N):
    """The full orchestrator must answer with a clean ingest reply."""
    global PASS, FAIL
    orch = Orchestrator()
    try:
        reply = orch.handle(f"demo-{label}", text)
    except Exception as exc:
        FAIL += 1
        print(f"  ❌ {label}: RAISED {type(exc).__name__}: {exc}")
        return
    if f"Parsed {expect_n} transactions" in reply:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}: unexpected reply: {reply[:70]!r}")


# ── G1. the baseline: the demo file as shipped ─────────────────────────
print("\n[G1] Baseline")
check("demo CSV has 38 data rows", DEMO_N == 38, f"got {DEMO_N}")
check("demo CSV total is $3,524.72", abs(DEMO_TOTAL - 3524.72) < 0.005,
      f"got ${DEMO_TOTAL:,.2f}")
check("demo CSV income is $7,500.00", abs(DEMO_INCOME - 7500.0) < 0.005,
      f"got ${DEMO_INCOME:,.2f}")
check("demo CSV spending is $3,975.28", abs(DEMO_SPEND - 3975.28) < 0.005,
      f"got ${DEMO_SPEND:,.2f}")
demo_check("clean demo CSV", DEMO_TEXT)
demo_money_check("clean demo CSV → money story", DEMO_TEXT)
demo_orch("clean demo CSV → orchestrator", DEMO_TEXT)

# ── G2. the same file, exported by a different tool ────────────────────
print("\n[G2] Export quirks (same 38 transactions)")
demo_check("CRLF line endings", DEMO_TEXT.replace("\n", "\r\n"))
demo_check("UTF-8 BOM", "﻿" + DEMO_TEXT)
demo_check("BOM + CRLF", "﻿" + DEMO_TEXT.replace("\n", "\r\n"))
demo_check("semicolon delimiter", render(DEMO_DATA, DEMO_HEADER, ";"))
demo_check("tab delimiter", render(DEMO_DATA, DEMO_HEADER, "\t"))
demo_check("pipe delimiter", render(DEMO_DATA, DEMO_HEADER, "|"))
demo_check("no header row", render(DEMO_DATA))
demo_check("columns reordered", render([[r[2], r[1], r[0]] for r in DEMO_DATA],
                                       ["Amount", "Description", "Date"]))
demo_check("extra Balance column", render([[r[0], r[1], r[2], "100.00"] for r in DEMO_DATA],
                                           ["Date", "Description", "Amount", "Balance"]))
demo_check("quoted fields with embedded commas",
           render([[r[0], r[1] + ", Inc.", r[2]] for r in DEMO_DATA], DEMO_HEADER))
demo_check("whitespace padding in every cell",
           render([[f"  {c}  " for c in r] for r in DEMO_DATA], DEMO_HEADER))
demo_check("blank lines around the file", "\n\n" + DEMO_TEXT + "\n\n")
demo_check("amounts with currency symbol and thousands separator",
           render([[r[0], r[1],
                    ("-$" if float(r[2]) < 0 else "$") + f"{abs(float(r[2])):,.2f}"]
                   for r in DEMO_DATA], DEMO_HEADER))
demo_check("European format (€ , decimal comma)",
           render([[r[0], r[1],
                    ("-€" if float(r[2]) < 0 else "€") +
                    f"{abs(float(r[2])):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")]
                   for r in DEMO_DATA], DEMO_HEADER))
demo_check("Dr/Cr suffixes instead of signs",
           render([[r[0], r[1], f"{abs(float(r[2])):.2f} {'DR' if float(r[2]) < 0 else 'CR'}"]
                   for r in DEMO_DATA], DEMO_HEADER))
demo_check("ISO dates",
           render([[datetime.datetime.strptime(r[0], "%m/%d/%Y").strftime("%Y-%m-%d"),
                    r[1], r[2]] for r in DEMO_DATA], DEMO_HEADER))
demo_check("debit/credit columns instead of a signed amount",
           render([[r[0], r[1],
                    f"{abs(float(r[2])):.2f}" if float(r[2]) < 0 else "",
                    f"{float(r[2]):.2f}" if float(r[2]) > 0 else ""] for r in DEMO_DATA],
                  ["Date", "Description", "Debit", "Credit"]))
demo_check("accented / non-ASCII merchants",
           render([[r[0], r[1] + " Café Ñoño", r[2]] for r in DEMO_DATA], DEMO_HEADER))

# ── G3. the money story must survive the export quirks ────────────────
print("\n[G3] The analysis is unchanged by the export quirks")
for label, text in [
    ("CRLF", DEMO_TEXT.replace("\n", "\r\n")),
    ("BOM", "﻿" + DEMO_TEXT),
    ("semicolon", render(DEMO_DATA, DEMO_HEADER, ";")),
    ("tab", render(DEMO_DATA, DEMO_HEADER, "\t")),
    ("pipe", render(DEMO_DATA, DEMO_HEADER, "|")),
    ("no header", render(DEMO_DATA)),
    ("reordered", render([[r[2], r[1], r[0]] for r in DEMO_DATA],
                          ["Amount", "Description", "Date"])),
    ("Dr/Cr suffixes", render([[r[0], r[1], f"{abs(float(r[2])):.2f} {'DR' if float(r[2]) < 0 else 'CR'}"]
                               for r in DEMO_DATA], DEMO_HEADER)),
]:
    demo_money_check(f"{label} → money story", text)

# ── G4. damaged rows ──────────────────────────────────────────────────
print("\n[G4] Damaged rows (bad row dropped, rest of the file survives)")
truncated = DEMO_TEXT.strip().split("\n")[:-1] + [DEMO_TEXT.strip().split("\n")[-1][:14]]
demo_check("truncated final row", "\n".join(truncated), expect_n=DEMO_N - 1,
           expect_total=DEMO_TOTAL - float(DEMO_DATA[-1][2]))
demo_check("row with a blank amount",
           render([[r[0], r[1], "" if i == 3 else r[2]] for i, r in enumerate(DEMO_DATA)],
                  DEMO_HEADER), expect_n=DEMO_N - 1,
           expect_total=DEMO_TOTAL - float(DEMO_DATA[3][2]))
demo_check("row with a garbage amount",
           render([[r[0], r[1], "abc" if i == 3 else r[2]] for i, r in enumerate(DEMO_DATA)],
                  DEMO_HEADER), expect_n=DEMO_N - 1,
           expect_total=DEMO_TOTAL - float(DEMO_DATA[3][2]))
demo_check("row with a blank date",
           render([["" if i == 3 else r[0], r[1], r[2]] for i, r in enumerate(DEMO_DATA)],
                  DEMO_HEADER))
demo_check("row with no description",
           render([[r[0], "" if i == 3 else r[1], r[2]] for i, r in enumerate(DEMO_DATA)],
                  DEMO_HEADER))
demo_check("null byte in a merchant name",
           render([[r[0], r[1].replace("Netflix", "Net\x00flix"), r[2]] for r in DEMO_DATA],
                  DEMO_HEADER))
demo_check("5000-character merchant name",
           render([[r[0], "X" * 5000, r[2]] for r in DEMO_DATA], DEMO_HEADER))
demo_check("every row duplicated", render(DEMO_DATA + DEMO_DATA, DEMO_HEADER),
           expect_n=DEMO_N * 2, expect_total=DEMO_TOTAL * 2)

# ── G5. the Phase 3.4 path: redact → paste ────────────────────────────
print("\n[G5] Redacted file (the Phase 3.4 workflow)")
try:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "redact_csv.py"), str(DEMO_PATH)],
        capture_output=True, text=True, timeout=120,
    )
    redacted = proc.stdout
except Exception as exc:
    redacted = ""
    FAIL += 1
    print(f"  ❌ redact_csv.py crashed: {type(exc).__name__}: {exc}")

if redacted:
    check("redaction removed the merchant names", "Netflix" not in redacted
          and "Whole Foods" not in redacted, "merchant names survived")
    demo_check("redacted demo CSV still parses", redacted)
    demo_orch("redacted demo CSV → orchestrator", redacted)
else:
    FAIL += 1
    print("  ❌ redact_csv.py produced no output")

# ── G6. nothing at all ────────────────────────────────────────────────
print("\n[G6] Empty and header-only files")
demo_check("header only", "\n".join(DEMO_HEADER), expect_n=0, expect_total=0.0)
demo_check("every row blank", "\n".join([",".join(DEMO_HEADER)] + [",,"] * DEMO_N),
           expect_n=0, expect_total=0.0)
sa_fe("demo header only", "\n".join(DEMO_HEADER), expect_ingest=False)
sa_fe("demo all-blank rows", "\n".join([",".join(DEMO_HEADER)] + [",,"] * DEMO_N),
      expect_ingest=False)

# ── summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 64)
sys.exit(0 if FAIL == 0 else 1)
