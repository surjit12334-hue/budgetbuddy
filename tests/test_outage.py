#!/usr/bin/env python3
"""Phase 3.3 — LLM-outage drill.

Simulates a provider outage mid-session and asserts the deterministic
insights take over silently: no crash, no error surfaced, still useful.

Two scenarios:
  A. Key present but provider fails (network/503)  → fallback
  B. Key removed mid-session                        → fallback

Run:  .venv/bin/python tests/test_outage.py
"""

import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.llm as llm_mod
from core.llm import LLMClient
from core.orchestrator import Orchestrator
from core.parser import parse_csv
from core.categorizer import Categorizer
from core.analyzer import Analyzer
from core.coach import Coach

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


CSV = (ROOT / "samples" / "sample_bank.csv").read_text()

print("=" * 64)
print("PHASE 3.3 — LLM-OUTAGE DRILL")
print("=" * 64)

# ── A. Provider fails while key is present ─────────────────────────────
print("\n[A] Key present, provider unreachable (simulated)")
os.environ["GEMINI_API_KEY"] = "fake-key-for-outage-test"

# Monkeypatch requests.post to always time out
import requests
_orig_post = requests.post


def _boom(*a, **kw):
    raise requests.exceptions.ReadTimeout("simulated provider outage")


requests.post = _boom
try:
    llm = LLMClient()
    check("llm.available True (key set)", llm.available is True)
    out = llm.generate("Say hi")
    check("generate() returns None on outage (no raise)", out is None)

    # Coach must still produce useful output
    txns = Categorizer(None).categorize_all(parse_csv(CSV))  # no LLM at all
    analysis = Analyzer().analyze(txns)
    msg = Coach(llm).get_insights(analysis)
    check("coach produced output during outage", len(msg) > 30)
    check("coach fell back to deterministic", "offline mode" in msg.lower(),
          f"got: {msg[:60]}")
    check("no traceback leaked into output", "Traceback" not in msg)
finally:
    requests.post = _orig_post

# ── B. Key removed mid-session ─────────────────────────────────────────
print("\n[B] Key removed mid-session")
orch = Orchestrator()
sid = "outage-si"

# Turn 1 with key present (but provider dead → fallback)
r1 = orch.handle(sid, CSV)
check("turn 1 ingest works with key", "Parsed 38" in r1, f"got {r1[:50]}")

# Now remove the key entirely
os.environ.pop("GEMINI_API_KEY", None)
orch.llm.gemini_key = ""
orch.llm._ollama_ok = False

r2 = orch.handle(sid, "How am I doing?")
check("turn 2 analysis works without key", "Financial Health" in r2, f"got {r2[:50]}")
check("turn 2 has insights", "savings" in r2.lower() or "Coach" in r2)
check("turn 2 no error text", "Traceback" not in r2 and "Error" not in r2)

r3 = orch.handle(sid, "What subscriptions do I have?")
check("turn 3 subscriptions works", "Recurring Subscriptions" in r3, f"got {r3[:50]}")

r4 = orch.handle(sid, "I want to save $3000 by August")
check("turn 4 goal works", "Savings Goal" in r4, f"got {r4[:50]}")

# ── C. Ride through: nothing surfaced an error ─────────────────────────
print("\n[C] Silence check — user never sees an LLM error")
for label, reply in [("analysis", r2), ("subscriptions", r3), ("goal", r4)]:
    leaked = any(w in reply.lower() for w in
                 ["traceback", "exception", "api key", "gemini error",
                  "connection error", "timeout error", "503", "500 internal"])
    check(f"{label}: no error leaked", not leaked, f"leak in: {reply[:60]!r}")

print("\n" + "=" * 64)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 64)
sys.exit(0 if FAIL == 0 else 1)
