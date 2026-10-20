#!/usr/bin/env python3
"""Redact a real bank CSV before sharing/testing (Phase 3.4 helper).

Keeps dates, amounts and structure; scrambles merchant text so the file
is safe to paste into the simulator or share.

Usage:
    .venv/bin/python tools/redact_csv.py my_real_export.csv > safe.csv
"""

import sys
import csv
import hashlib
import pathlib

# Deterministic fake merchant names
FAKE = [
    "Merchant A", "Merchant B", "Merchant C", "Merchant D", "Merchant E",
    "Store X", "Store Y", "Cafe Z", "Service Co", "Utility Inc",
]


def fake_name(raw: str) -> str:
    h = hashlib.sha256(raw.encode()).hexdigest()
    return FAKE[int(h[:8], 16) % len(FAKE)]


def redact(path: str) -> None:
    text = pathlib.Path(path).read_text()
    # Detect delimiter
    first = text.strip().splitlines()[0]
    delim = max([",", ";", "\t", "|"], key=first.count)

    reader = csv.reader(text.splitlines(), delimiter=delim)
    writer = csv.writer(sys.stdout)
    for i, row in enumerate(reader):
        if i == 0:
            writer.writerow(row)  # header unchanged
            continue
        out = []
        for cell in row:
            c = cell.strip()
            # Keep numbers/dates/currency as-is; scramble long text
            digits = sum(ch.isdigit() for ch in c)
            if len(c) > 4 and digits < len(c) / 2:
                out.append(fake_name(c))
            else:
                out.append(cell)
        writer.writerow(out)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: redact_csv.py <path/to/real_export.csv>", file=sys.stderr)
        sys.exit(2)
    redact(sys.argv[1])


if __name__ == "__main__":
    main()
