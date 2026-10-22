#!/usr/bin/env bash
# run_tests.sh — run the whole test suite and print one summary.
#
#   ./run_tests.sh
#
# Each test file prints its own "RESULTS: N passed, M failed" line; this
# runs them all and adds up the totals.  Exits non-zero if any file
# fails, so it can be used as a CI gate.

set -uo pipefail

cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "❌ No venv found. Run:"
  echo "   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

total_p=0
total_f=0
failed_files=0

for f in tests/*.py; do
  base=$(basename "$f")
  [ "$base" = "demo.py" ] && continue
  out=$(timeout 300 "$PYTHON" "$f" 2>&1)
  code=$?
  line=$(printf '%s' "$out" | grep -Eo "RESULTS: [0-9]+ passed, [0-9]+ failed" | tail -1)
  p=$(printf '%s' "$line" | grep -Eo "[0-9]+ passed" | grep -Eo "[0-9]+")
  fl=$(printf '%s' "$line" | grep -Eo "[0-9]+ failed" | grep -Eo "[0-9]+")
  printf "%-28s exit=%s  %s\n" "$base" "$code" "${line:-<no RESULTS line>}"
  total_p=$((total_p + ${p:-0}))
  total_f=$((total_f + ${fl:-0}))
  if [ "$code" != "0" ]; then
    failed_files=$((failed_files + 1))
    printf '%s\n' "$out" | grep -E "❌|FAIL|Error|Traceback" | head -8
  fi
done

echo "--------------------------------------"
echo "TOTAL: $total_p passed, $total_f failed ($failed_files file(s) non-zero)"

if [ "$total_f" != "0" ] || [ "$failed_files" != "0" ]; then
  exit 1
fi
