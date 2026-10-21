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

PORT="${HOST_PORT:-8001}"
LOCKFILE="/tmp/budgetbuddy-keepalive-${PORT}.lock"

# ── single-instance guard ─────────────────────────────────────────────
# Two keepalives fighting over the same port is a self-inflicted outage:
# each restarts the other's Bureau and they crash-loop on
# "[Errno 98] address already in use".  Take an exclusive lock so only
# one keepalive can supervise a given port.
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "❌ Another keepalive is already supervising port $PORT."
  echo "   (lock: $LOCKFILE)  Nothing to do — refusing to start a second one."
  exit 1
fi
echo $$ > "$LOCKFILE"

# ── reap a stale Bureau holding the port ──────────────────────────────
# Without this, a leftover `agents.run` keeps port $PORT bound, every new
# instance dies with [Errno 98] address already in use, and keepalive
# spins forever. Find the holder via /proc (no lsof dependency).
port_holder() {
  for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
    [ -r "/proc/$pid/cmdline" ] || continue
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "agents\.run" || continue
    grep -qa ":$(printf '%04X' "$PORT")" "/proc/$pid/net/tcp" 2>/dev/null && echo "$pid"
  done
}

for pid in $(port_holder); do
  echo "⚠️  killing stale Bureau (pid $pid) holding port $PORT"
  kill -9 "$pid" 2>/dev/null || true
done
sleep 1

# Wait for the port to actually be released.  A just-killed Bureau can
# hold the socket in TIME_WAIT for a moment; starting the replacement
# too early is exactly the "address already in use" crash loop.
for _ in $(seq 1 20); do
  if ! ss -ltn 2>/dev/null | grep -q ":${PORT}\b"; then
    break
  fi
  sleep 0.5
done

echo "♻️  BudgetBuddy keepalive — Ctrl-C to stop"
while true; do
  echo "[$(date '+%H:%M:%S')] starting Bureau…"
  "$PYTHON" -u -m agents.run
  code=$?
  if [ "$code" -eq 0 ]; then
    echo "[$(date '+%H:%M:%S')] Bureau stopped cleanly — not restarting"
    exit 0
  fi
  echo "[$(date '+%H:%M:%S')] Bureau exited (code $code) — restarting in 3s"
  sleep 3
done
