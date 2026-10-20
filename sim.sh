#!/usr/bin/env bash
# Launch the BudgetBuddy local simulator (Phase 3.1).
#
#   ./sim.sh
#
# Loads .env if present, then starts the terminal REPL.

set -euo pipefail

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

exec "$PYTHON" run_local.py
