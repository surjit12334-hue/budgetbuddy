#!/usr/bin/env bash
# keepalive.sh — restart the Bureau if it ever exits (Phase 5.6).
#
#   ./keepalive.sh
#
# Use this for the demo window so a crash doesn't take the agent offline.
# Ctrl-C stops the loop.

set -uo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "❌ No venv found. Run:"
  echo "   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

trap 'echo; echo "👋 keepalive stopping"; exit 0' INT TERM

echo "♻️  BudgetBuddy keepalive — Ctrl-C to stop"
while true; do
  echo "[$(date '+%H:%M:%S')] starting Bureau…"
  "$PYTHON" -u -m agents.run
  code=$?
  echo "[$(date '+%H:%M:%S')] Bureau exited (code $code) — restarting in 3s"
  sleep 3
done
