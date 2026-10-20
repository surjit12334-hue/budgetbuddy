#!/usr/bin/env python3
"""Phase 5 preflight — verify everything is ready before ASI:One.

Checks, in order:
  1. Bureau is running (GET /health)
  2. All 6 agents are registered
  3. Local REPLY: POST /submit round-trips
  4. End-to-end 6-turn flow works over the endpoint
  5. Session persistence (turn 2 remembers turn 1)
  6. Agentverse registration: status active, mailbox endpoint

Usage:
    .venv/bin/python tools/preflight.py

Exit code 0 = all green, 1 = something needs fixing.
"""

import json
import sys
import urllib.request
import urllib.error
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL = "http://localhost:8001"

GREEN, RED, YEL, RST = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def ok(msg):
    print(f"  {GREEN}✅ {msg}{RST}")


def bad(msg):
    print(f"  {RED}❌ {msg}{RST}")


def warn(msg):
    print(f"  {YEL}⚠️  {msg}{RST}")


def get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "budgetbuddy-preflight/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def post(url, payload, timeout=40):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask(base, session_id, text):
    return post(f"{base}/submit", {"session_id": session_id, "text": text})["reply"]


def main():
    base = LOCAL

    print("=" * 62)
    print("  BUDGETBUDDY — PHASE 5 PREFLIGHT")
    print("=" * 62)
    failures = 0

    # ── 1. Bureau up ───────────────────────────────────────────────────
    print(f"\n[1] Bureau reachable at {LOCAL}")
    health = None
    try:
        health = get(f"{LOCAL}/health")
        ok("Bureau responded to GET /health")
    except Exception as e:
        bad(f"Bureau not reachable: {e}")
        print("\n  → Start it first:  ./run.sh")
        failures += 1

    # ── 2. Agents registered ───────────────────────────────────────────
    if health:
        print(f"\n[2] Agents registered")
        agents = health.get("agents", {})
        for name in ("host", "ingest", "analyst", "coach", "goal", "splitter"):
            addr = agents.get(name)
            if addr and addr.startswith("agent1"):
                ok(f"{name:<9} {addr[:30]}…")
            else:
                bad(f"{name:<9} missing")
                failures += 1
        print(f"     session TTL: {health.get('session_ttl_hours')}h")

    # ── 3. Local round-trip ────────────────────────────────────────────
    if health:
        print("\n[3] Local POST /submit round-trip")
        try:
            reply = ask(LOCAL, "preflight-1", "Help")
            if isinstance(reply, str) and reply.strip():
                ok(f"got a reply ({len(reply)} chars)")
            else:
                bad("empty reply")
                failures += 1
        except Exception as e:
            bad(f"submit failed: {e}")
            failures += 1

    # ── 4. End-to-end 6-turn flow ──────────────────────────────────────
    if health:
        print("\n[4] End-to-end 6-turn flow")
        csv_text = (ROOT / "samples" / "sample_bank.csv").read_text()
        sid = "preflight-e2e"
        checks = [
            ("ingest", csv_text, "Parsed"),
            ("analysis", "How am I doing?", "Financial Health"),
            ("subscriptions", "What subscriptions do I have?", "Recurring Subscriptions"),
            ("goal", "I want to save $3000 by August", "Savings Goal"),
            ("split", "Split this $90 dinner with Alice and Bob", "Split"),
            ("payment", "How do I unlock Pro?", "Payment Request"),
        ]
        for label, text, expect in checks:
            try:
                reply = ask(LOCAL, sid, text)
                if expect in reply:
                    ok(f"turn {label}")
                else:
                    bad(f"turn {label}: expected '{expect}' — got {reply[:50]!r}")
                    failures += 1
            except Exception as e:
                bad(f"turn {label}: {e}")
                failures += 1

    # ── 5. Session persistence ─────────────────────────────────────────
    if health:
        print("\n[5] Session persistence")
        try:
            sid = "preflight-persist"
            ask(LOCAL, sid, "01/15/2024,Coffee,-5.45\n01/16/2024,Netflix,-15.99")
            reply = ask(LOCAL, sid, "How am I doing?")
            if "Financial Health" in reply:
                ok("turn 2 remembered turn 1's data")
            else:
                bad(f"memory lost — got {reply[:60]!r}")
                failures += 1
            # Different session must NOT see it
            fresh = ask(LOCAL, "preflight-fresh", "How am I doing?")
            if "don't have any transactions" in fresh:
                ok("sessions are isolated")
            else:
                warn(f"fresh session saw data? {fresh[:50]!r}")
        except Exception as e:
            bad(f"persistence check failed: {e}")
            failures += 1

    # ── 6. Agentverse registration ─────────────────────────────────────
    if health:
        print("\n[6] Agentverse registration (Almanac)")
        host_addr = health.get("agents", {}).get("host", "")
        almanac = f"https://agentverse.ai/v1/almanac/agents/{host_addr}"
        reg = None
        try:
            reg = get(almanac, timeout=20)
        except Exception as e:
            warn(f"could not reach Almanac ({e})")
            print("     → Needs internet. Registration happens at startup;")
            print("       retry in a few seconds if the agent just booted.")
        if reg is not None:
            status = reg.get("status")
            rtype = reg.get("type")
            protos = reg.get("protocols") or []
            if status == "active" and rtype == "mailbox":
                ok(f"agent is active as a mailbox ({len(protos)} protocols)")
            elif status == "active":
                ok(f"agent is active (type={rtype!r})")
            else:
                bad(f"agent is not active (status={status!r}) — retry shortly")
                failures += 1
            print(f"     profile: https://agentverse.ai/agents/details/{host_addr}")
            print("     → If you see 'mailbox not found' in the Bureau log,")
            print("       create the mailbox in the Agentverse Agent Inspector.")

    # ── summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    if failures == 0:
        print(f"  {GREEN}✅ ALL CHECKS PASSED — ready for ASI:One{RST}")
    else:
        print(f"  {RED}❌ {failures} check(s) failed — fix before ASI:One{RST}")
    print("=" * 62)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
