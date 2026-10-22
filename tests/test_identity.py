#!/usr/bin/env python3
"""Identity tests — every process must resolve the SAME agent.

Real bug this guards against: an agent's address is a pure function of
its seed, so a process that resolves a different seed talks to a
different agent.  ``agents/identity.py`` used to record the resolved
addresses into ``.budgetbuddy_identity`` at *import* time, so any
process that merely imported ``agents.host`` — including
``tests/test_inspector.py``, which ``./run_tests.sh`` runs without
sourcing ``.env`` — overwrote the file with the per-machine fallback
seed's address:

    agent1q0npvcj…   ← written by the test run, NOT registered on Agentverse
    agent1qwtj4vk…   ← the live agent (from .env HOST_SEED), IS registered

``tools/card_demo.py`` and ``tools/payment_demo.py`` read that file to
find the seller, so after any test run they would have talked to an
agent that does not exist — and the live payment demo would fail with
no obvious reason.

Run:  .venv/bin/python tests/test_identity.py
"""

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASSED = 0
FAILED = 0

IDENTITY_FILE = ROOT / ".budgetbuddy_identity"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


def main() -> int:
    print("=" * 60)
    print("  IDENTITY — one seed, one agent, everywhere")
    print("=" * 60)

    # ── 1. the seed is the same in every process ──────────────────────
    print("\n[1] Seed resolution")
    from agents.identity import resolve_seed, derived_address, known_address

    seed_here = resolve_seed("host")
    check("host seed resolves to a non-placeholder value",
          bool(seed_here) and "replace with" not in seed_here, seed_here)

    # A process with a *different* environment must still resolve the
    # same seed, because agents/identity.py loads .env itself.
    env = dict(os.environ)
    env.pop("HOST_SEED", None)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);"
         "from agents.identity import resolve_seed, derived_address;"
         "print(resolve_seed('host'));"
         "print(derived_address('host'))" % str(ROOT)],
        capture_output=True, text=True, env=env, timeout=120,
    )
    other_seed = proc.stdout.strip().splitlines()
    check("a process without HOST_SEED in its env resolves the same seed",
          len(other_seed) == 2 and other_seed[0] == seed_here,
          f"here={seed_here!r} there={other_seed[:1]!r} err={proc.stderr[-160:]!r}")

    live = derived_address("host")
    check("the host address is derived deterministically",
          bool(live) and live.startswith("agent1q"), live or "none")
    if len(other_seed) == 2:
        check("both processes derive the same host address",
              other_seed[1] == live, f"{other_seed[1]} vs {live}")

    # ── 2. the recorded file agrees with the derived address ─────────
    print("\n[2] A stale .budgetbuddy_identity cannot mislead the tools")
    recorded = {}
    if IDENTITY_FILE.exists():
        try:
            recorded = json.loads(IDENTITY_FILE.read_text()).get("addresses") or {}
        except ValueError:
            recorded = {}
    check("known_address('host') == derived_address('host')",
          known_address("host") == live, f"{known_address('host')} vs {live}")

    # Reproduce the exact failure: a file that names an agent which is
    # NOT the live one must not be handed to the demo tools.
    if IDENTITY_FILE.exists():
        original = IDENTITY_FILE.read_text()
        try:
            data = json.loads(original)
            data.setdefault("addresses", {})["host"] = "agent1qNOTAREALADDRESS"
            IDENTITY_FILE.write_text(json.dumps(data, indent=2) + "\n")
            check("a stale file does not hijack known_address('host')",
                  known_address("host") == live,
                  f"{known_address('host')} vs {live}")
        finally:
            IDENTITY_FILE.write_text(original)
        check("the file was restored", IDENTITY_FILE.read_text() == original)
    else:
        check("a stale file does not hijack known_address('host')",
              known_address("host") == live)

    # ── 3. importing the host module must NOT clobber the file ────────
    print("\n[3] Importing agents.host does not rewrite the identity file")
    before = IDENTITY_FILE.read_text() if IDENTITY_FILE.exists() else None
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys, asyncio; sys.path.insert(0, %r);"
         "asyncio.set_event_loop(asyncio.new_event_loop());"
         "import agents.host" % str(ROOT)],
        capture_output=True, text=True, env=env, timeout=180,
    )
    check("importing agents.host succeeds", proc.returncode == 0,
          proc.stderr[-200:])
    after = IDENTITY_FILE.read_text() if IDENTITY_FILE.exists() else None
    check("the identity file is untouched by an import",
          before == after,
          "the file was rewritten — the demo tools can be pointed at a "
          "non-existent agent")

    # ── 4. the demo tools target the live agent ───────────────────────
    print("\n[4] The demo tools target the live agent")
    from agents.identity import live_bureau_address

    live_bureau = live_bureau_address("host")
    if live_bureau:
        check("the running Bureau reports its host address",
              live_bureau.startswith("agent1q"), live_bureau)
        target = live_bureau
    else:
        print("     (no Bureau running on this port — using the derived address)")
        target = live

    for tool in ("tools/card_demo.py", "tools/payment_demo.py"):
        path = ROOT / tool
        if not path.exists():
            check(f"{tool} exists", False, "missing")
            continue
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r);"
             "import importlib;"
             "m = importlib.import_module(%r);"
             "print(m.HOST_ADDRESS)" % (str(ROOT), tool[:-3].replace("/", "."))],
            capture_output=True, text=True, env=env, timeout=180,
        )
        got = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        check(f"{tool} targets the live host address",
              got == target, f"tool={got} live={target} err={proc.stderr[-160:]!r}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
