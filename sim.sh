#!/usr/bin/env bash
# Launch the BudgetBuddy local simulator (Phase 3.1).
#
#   ./sim.sh
#
# Loads .env if present, then starts the terminal REPL.

set -euo pipefail

cd "$(dirname "$0")"

# Load .env if present (an already-exported variable wins over the file)
# shellcheck disable=SC1091
source ./env.sh
load_env .env

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "❌ No venv found. Run:"
  echo "   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

exec "$PYTHON" run_local.py
