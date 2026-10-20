#!/usr/bin/env python3
"""BudgetBuddy — local terminal simulator (Phase 3).

A REPL that talks to the Phase 1 brain directly (no agents, no network),
so you can exercise the full 6-turn demo in seconds.

Usage:
    .venv/bin/python run_local.py

Commands (type at the prompt):
    /demo      run the full 6-turn demo with sample data
    /reset     wipe the current session
    /paste     enter multi-line paste mode (end with a lone '.' on a line)
    /help      show commands
    /quit      exit
"""

import sys
import pathlib
import uuid

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.orchestrator import Orchestrator  # noqa: E402

BANNER = """\
╔══════════════════════════════════════════════════════════╗
║  BudgetBuddy — local simulator                           ║
║  Your AI budget coach. Paste data or ask a question.     ║
╚══════════════════════════════════════════════════════════╝
Type /help for commands, /demo for the full walkthrough.
"""

HELP = """\
Commands:
  /demo    run the full 6-turn demo with sample data
  /reset   wipe the current session (fresh start)
  /paste   multi-line paste mode — end with a lone '.' line
  /help    show this message
  /quit    exit

Or just type naturally:
  • paste a CSV or list of transactions
  • "How am I doing?"
  • "What subscriptions do I have?"
  • "I want to save $3000 by August"
  • "Split this $90 dinner with Alice and Bob"
  • "How do I unlock Pro?"
"""


class LocalSim:
    def __init__(self):
        self.orch = Orchestrator()
        self.session_id = f"local-{uuid.uuid4().hex[:8]}"
        self.sample_csv = (ROOT / "samples" / "sample_bank.csv").read_text()

    # ── output helpers ─────────────────────────────────────────────────

    @staticmethod
    def _reply(text: str):
        print()
        print("─" * 60)
        print(text)
        print("─" * 60)
        print()

    # ── commands ───────────────────────────────────────────────────────

    def cmd_demo(self):
        turns = [
            ("Paste sample bank CSV", self.sample_csv),
            ("How am I doing?", None),
            ("What subscriptions do I have?", None),
            ("I want to save $3000 by August", None),
            ("Split this $90 dinner with Alice and Bob", None),
            ("How do I unlock Pro?", None),
        ]
        for i, (label, text) in enumerate(turns, 1):
            actual = text if text is not None else label
            shown = label if text is not None else label
            print(f"\n▶ Turn {i}: {shown}")
            reply = self.orch.handle(self.session_id, actual)
            self._reply(reply)
        print("✅ Demo complete.\n")

    def cmd_reset(self):
        self.orch.store.purge_all()
        self.session_id = f"local-{uuid.uuid4().hex[:8]}"
        print(f"\n🔄 Session reset. New session: {self.session_id}\n")

    def cmd_paste(self):
        print("\n📋 Paste mode — enter your data, then a lone '.' to send:\n")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == ".":
                break
            lines.append(line)
        text = "\n".join(lines)
        if not text.strip():
            print("\n(empty paste — nothing sent)\n")
            return
        self._reply(self.orch.handle(self.session_id, text))

    # ── main loop ──────────────────────────────────────────────────────

    def run(self):
        print(BANNER)
        while True:
            try:
                raw = input("you ▸ ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n👋 Bye!")
                return

            if not raw:
                continue

            if raw.startswith("/"):
                cmd = raw.lower()
                if cmd in ("/quit", "/exit", "/q"):
                    print("\n👋 Bye!")
                    return
                if cmd == "/help":
                    print("\n" + HELP)
                elif cmd == "/demo":
                    self.cmd_demo()
                elif cmd == "/reset":
                    self.cmd_reset()
                elif cmd == "/paste":
                    self.cmd_paste()
                else:
                    print(f"\n❓ Unknown command: {raw}  (try /help)\n")
                continue

            # Natural-language / data turn
            try:
                reply = self.orch.handle(self.session_id, raw)
            except Exception as exc:  # never crash the REPL
                reply = (
                    "😅 Sorry, something went wrong processing that.\n"
                    f"({type(exc).__name__}: {exc})\n"
                    "Try re-pasting your data, or type /help."
                )
            self._reply(reply)


def main():
    LocalSim().run()


if __name__ == "__main__":
    main()
