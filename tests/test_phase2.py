#!/usr/bin/env python3
"""Phase 2 integration test — sends the full 6-turn flow over HTTP
to the running Bureau and verifies multi-agent orchestration."""

import json
import sys
import urllib.request
import pathlib

BASE = "http://localhost:8001/submit"
ROOT = pathlib.Path(__file__).resolve().parent.parent

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


def send(session_id: str, text: str) -> str:
    payload = json.dumps({"session_id": session_id, "text": text}).encode()
    req = urllib.request.Request(
        BASE, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["reply"]


csv_text = (ROOT / "samples" / "sample_bank.csv").read_text()
sid = "phase2-test"

print("=" * 60)
print("PHASE 2 INTEGRATION TEST")
print("=" * 60)

# Turn 1 — ingest
r1 = send(sid, csv_text)
check("turn 1: ingest 38 txns", "Parsed 38" in r1, f"got: {r1[:80]}")

# Turn 2 — analysis
r2 = send(sid, "How am I doing?")
check("turn 2: analysis", "Financial Health" in r2, f"got: {r2[:80]}")
check("turn 2: insights present", "savings" in r2.lower() or "Coach" in r2)

# Turn 3 — subscriptions
r3 = send(sid, "What subscriptions do I have?")
check("turn 3: subscriptions", "Recurring Subscriptions" in r3, f"got: {r3[:80]}")

# Turn 4 — goal
r4 = send(sid, "I want to save $3000 by August")
check("turn 4: goal plan", "Savings Goal" in r4, f"got: {r4[:80]}")

# Turn 5 — split
r5 = send(sid, "Split this $90 dinner with Alice and Bob")
check("turn 5: split", "Split" in r5 and "Alice" in r5, f"got: {r5[:80]}")

# Turn 6 — payment
r6 = send(sid, "How do I unlock Pro?")
check("turn 6: payment", "Payment Request" in r6, f"got: {r6[:80]}")

print()
print("=" * 60)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
