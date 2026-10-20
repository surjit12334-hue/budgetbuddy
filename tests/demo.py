#!/usr/bin/env python3
"""Demo: run the full 6-turn conversation and print each exchange."""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.orchestrator import Orchestrator

orch = Orchestrator()
sid = "demo-run"
csv_text = (ROOT / "samples" / "sample_bank.csv").read_text()

turns = [
    ("👤 You", csv_text),
    ("👤 You", "How am I doing?"),
    ("👤 You", "What subscriptions do I have?"),
    ("👤 You", "I want to save $3000 by August"),
    ("👤 You", "Split this $90 dinner with Alice and Bob"),
    ("👤 You", "How do I unlock Pro?"),
]

for i, (who, text) in enumerate(turns, 1):
    # Show first line only for CSV paste
    display = text if len(text) < 80 else text[:77] + "..."
    print(f"\n{'='*60}")
    print(f"TURN {i}: {who}")
    print(f"{'='*60}")
    print(f"{display}")
    print(f"\n{'─'*60}")
    reply = orch.handle(sid, text)
    print(reply)
