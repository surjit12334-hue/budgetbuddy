#!/usr/bin/env bash
# Start BudgetBuddy — the multi-agent ACP system.
#
#   ./run.sh          # start the Bureau on HOST_PORT (default 8001)
#
# Requires the venv from Phase 0:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

set -euo pipefail

cd "$(dirname "$0")"

# Load .env if present
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

exec "$PYTHON" -m agents.run
