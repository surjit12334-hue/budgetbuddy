#!/usr/bin/env bash
# stop_bureau.sh — stop the keepalive supervisor and the Bureau it runs.
#
# Kept in a file (rather than an inline shell loop) so the pattern being
# matched never appears in the invoking shell's own command line — an
# inline `pkill -f agents.run` happily matches the shell running it and
# kills the caller.
set -uo pipefail

stop() {
  for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
    [ -r "/proc/$pid/cmdline" ] || continue
    [ "$pid" = "$$" ] && continue
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null)
    cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
    case "$exe" in
      *bash)
        case "$cl" in
          *"./keepalive.sh"*|*"/keepalive.sh "*) echo "stop keepalive $pid"; kill -9 "$pid" 2>/dev/null ;;
        esac
        ;;
      *python*)
        case "$cl" in
          *"-m agents.run"*) echo "stop bureau $pid"; kill -9 "$pid" 2>/dev/null ;;
        esac
        ;;
    esac
  done
}

stop
sleep 2
stop
sleep 1

if ss -ltn 2>/dev/null | grep -q ":${1:-8001}\b"; then
  echo "⚠️  port ${1:-8001} is still held"
else
  echo "✅ port ${1:-8001} is free"
fi
