"""CSV & free-text → normalized Transaction objects.

Handles: delimiter detection, header mapping, 9+ date formats,
debit/credit columns, parenthesized negatives, currency symbols,
and ambiguity flags.
"""

import re
import csv
import io
from datetime import datetime
from typing import List, Tuple, Optional, Dict

from .models import Transaction

# ──────────────────────────── constants ────────────────────────────────

DATE_FORMATS = [
    "%m/%d/%Y",   # 01/15/2024   (US slash)
    "%d/%m/%Y",   # 15/01/2024   (EU slash)
    "%Y-%m-%d",   # 2024-01-15   (ISO)
    "%d-%m-%Y",   # 15-01-2024   (EU dash)
    "%m-%d-%Y",   # 01-15-2024   (US dash)
    "%Y/%m/%d",   # 2024/01/15   (slash ISO)
    "%b %d, %Y",  # Jan 15, 2024
    "%d %b %Y",   # 15 Jan 2024
    "%B %d, %Y",  # January 15, 2024
    "%d %B %Y",   # 15 January 2024
]

# symbol → currency code
CURRENCY_SYMBOLS: Dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "¥": "JPY",
    "C$": "CAD",
    "A$": "AUD",
}

# header alias → canonical field
KNOWN_HEADERS: Dict[str, List[str]] = {
    "date":        ["date", "transaction date", "posting date", "value date",
                     "datetime", "time", "trans date", "txn date"],
    "description": ["description", "memo", "details", "narrative", "particulars",
                     "reference", "transaction", "payee", "merchant", "name", "info",
                     "transaction description"],
    "amount":      ["amount", "value", "sum", "total", "transaction amount"],
    "debit":       ["debit", "withdrawal", "withdrawals", "dr", "paid out",
                     "out", "debit amount"],
    "credit":      ["credit", "deposit", "deposits", "cr", "paid in",
                     "in", "credit amount"],
    "balance":     ["balance", "running balance", "remaining"],  # ignored
}

# ──────────────────────────── helpers ──────────────────────────────────


def detect_delimiter(text: str) -> str:
    """Pick the most likely delimiter by inspecting the first few lines."""
    lines = text.strip().splitlines()[:5]
    best_char, best_score = ",", 0
    for delim in (",", ";", "\t", "|"):
        score = sum(line.count(delim) for line in lines)
        if score > best_score:
            best_char, best_score = delim, score
    return best_char


def parse_date(date_str: str) -> Tuple[Optional[datetime], bool]:
    """Return (datetime, is_ambiguous).  is_ambiguous=True when day/month could be swapped."""
    date_str = date_str.strip()
    if not date_str:
        return None, False

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
        except ValueError:
            continue

        # Ambiguity: numeric formats where both parts ≤ 12 and differ
        is_ambiguous = False
        if fmt in ("%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%m-%d-%Y"):
            parts = re.split(r"[/\-]", date_str)
            if len(parts) == 3:
                try:
                    a, b = int(parts[0]), int(parts[1])
                    if a != b and a <= 12 and b <= 12:
                        is_ambiguous = True
                except ValueError:
                    pass
        return dt, is_ambiguous

    return None, False


def parse_amount(amount_str: str) -> Tuple[Optional[float], str]:
    """Return (signed_value, currency_code).  None on unparseable."""
    if not amount_str:
        return None, "USD"

    s = amount_str.strip()
    currency = "USD"

    # Detect currency from symbol
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in s:
            currency = code
            break

    # Strip currency symbols / codes / Dr-Cr suffixes
    s = re.sub(r"(C\$|A\$|\$|€|£|₹|¥)", "", s)
    s = re.sub(r"\b(USD|EUR|GBP|INR|JPY|CAD|AUD)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Dr|Cr|DEBIT|CREDIT)\b\.?\s*$", "", s, flags=re.IGNORECASE)
    s = s.strip()

    # Parenthesised negatives: (50.00)
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()

    # Remove thousands separators
    s = s.replace(",", "").strip()

    # Explicit sign
    if s.startswith("-"):
        is_negative = not is_negative
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]

    try:
        value = float(s)
        return (-value if is_negative else value), currency
    except ValueError:
        return None, currency


def _looks_like_date(s: str) -> bool:
    return parse_date(s)[0] is not None


def _looks_like_amount(s: str) -> bool:
    return parse_amount(s.strip())[0] is not None


# ──────────────────────── header / column mapping ─────────────────────


def _detect_header_and_map(rows: List[List[str]]) -> Tuple[bool, Dict[str, int]]:
    if not rows:
        return False, {}
    header = [c.strip().lower() for c in rows[0]]
    mapping: Dict[str, int] = {}
    for field, aliases in KNOWN_HEADERS.items():
        for i, cell in enumerate(header):
            if cell in aliases:
                mapping[field] = i
                break
    has_header = "date" in mapping and ("description" in mapping or "amount" in mapping)
    return has_header, mapping


def _positional_map(rows: List[List[str]]) -> Dict[str, int]:
    """Guess column meaning from data rows when there is no header."""
    mapping: Dict[str, int] = {}
    if not rows:
        return mapping
    ncols = max(len(r) for r in rows)
    sample = rows[: min(10, len(rows))]

    for col in range(ncols):
        date_hits = amt_hits = 0
        for row in sample:
            if col < len(row):
                cell = row[col].strip()
                if _looks_like_date(cell):
                    date_hits += 1
                elif _looks_like_amount(cell):
                    amt_hits += 1
        n = len(sample)
        if date_hits > n * 0.5 and "date" not in mapping:
            mapping["date"] = col
        elif amt_hits > n * 0.5:
            # first amount-like column → amount (or debit; we only need one)
            for key in ("amount", "debit", "credit"):
                if key not in mapping:
                    mapping[key] = col
                    break

    # Description = widest text column not already claimed
    best_col, best_len = -1, 0
    for col in range(ncols):
        if col in mapping.values():
            continue
        avg = sum(len(r[col]) if col < len(r) else 0 for r in sample) / n
        if avg > best_len:
            best_col, best_len = col, avg
    if best_col >= 0 and "description" not in mapping:
        mapping["description"] = best_col

    return mapping


# ──────────────────────────── CSV parser ───────────────────────────────


def parse_csv(text: str) -> List[Transaction]:
    text = text.strip()
    if not text:
        return []

    delim = detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return []

    has_header, mapping = _detect_header_and_map(rows)
    if has_header:
        data_rows = rows[1:]
    else:
        mapping = _positional_map(rows)
        data_rows = rows

    transactions: List[Transaction] = []
    for row in data_rows:
        # ── date ──
        date_str = ""
        if "date" in mapping and mapping["date"] < len(row):
            date_str = row[mapping["date"]].strip()
        date, is_amb = parse_date(date_str) if date_str else (None, False)
        if date is None:
            date = datetime.now()

        # ── description ──
        desc = ""
        if "description" in mapping and mapping["description"] < len(row):
            desc = row[mapping["description"]].strip()

        # ── amount ──
        amount: Optional[float] = None
        currency = "USD"

        if "debit" in mapping or "credit" in mapping:
            debit_val = credit_val = None
            if "debit" in mapping and mapping["debit"] < len(row):
                debit_val, cur_d = parse_amount(row[mapping["debit"]].strip())
                if cur_d != "USD":
                    currency = cur_d
            if "credit" in mapping and mapping["credit"] < len(row):
                credit_val, cur_c = parse_amount(row[mapping["credit"]].strip())
                if cur_c != "USD":
                    currency = cur_c
            if credit_val and credit_val > 0:
                amount = abs(credit_val)
            elif debit_val is not None:
                amount = -abs(debit_val)
        elif "amount" in mapping and mapping["amount"] < len(row):
            amount, currency = parse_amount(row[mapping["amount"]].strip())

        if amount is None:
            continue

        transactions.append(
            Transaction(
                date=date,
                amount=amount,
                description=desc,
                currency=currency,
                is_ambiguous_date=is_amb,
                raw_line=delim.join(row),
            )
        )

    return transactions


# ──────────────────────────── free-text parser ─────────────────────────

# Match a currency-prefixed or suffixed number
_AMT_RE = re.compile(
    r"(?:[€£₹¥$]\s?[\d,]+\.?\d*"
    r"|\b[\d,]+\.\d{2}\s?(?:dollars|usd|eur|gbp|inr)\b)",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b")

_SPENT_WORDS = re.compile(
    r"\b(spent|paid|bought|purchase|withdrawal|debit|charged|order)\b", re.IGNORECASE
)
_EARNED_WORDS = re.compile(
    r"\b(received|earned|deposit|credit|income|refund|cashback|reward)\b", re.IGNORECASE
)


def parse_freetext(text: str) -> List[Transaction]:
    transactions: List[Transaction] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # amount
        m = _AMT_RE.search(line)
        if not m:
            # fall back: any bare number that looks like money
            m = re.search(r"\b\d+[.,]\d{2}\b", line)
        if not m:
            continue

        amount, currency = parse_amount(m.group(0))
        if amount is None:
            continue

        # sign
        if _SPENT_WORDS.search(line):
            amount = -abs(amount)
        elif _EARNED_WORDS.search(line):
            amount = abs(amount)

        # date
        date = datetime.now()
        is_amb = False
        dm = _DATE_RE.search(line)
        if dm:
            parsed, is_amb = parse_date(dm.group(0))
            if parsed:
                date = parsed

        # description: strip amount + date + filler words
        desc = line
        desc = _AMT_RE.sub("", desc)
        desc = _DATE_RE.sub("", desc)
        desc = re.sub(
            r"\b(spent|paid|bought|purchase|on|for|received|earned|the|a|an|my)\b",
            "",
            desc,
            flags=re.IGNORECASE,
        )
        desc = re.sub(
            r"\b(yesterday|today|tomorrow)\b", "", desc, flags=re.IGNORECASE
        )
        desc = re.sub(r"[\s,.\-:]+$", "", desc.strip())
        if not desc:
            desc = "Unknown"

        transactions.append(
            Transaction(
                date=date,
                amount=amount,
                description=desc,
                currency=currency,
                is_ambiguous_date=is_amb,
                raw_line=line,
            )
        )

    return transactions


# ──────────────────────────── unified entry ────────────────────────────


def parse_any(text: str) -> List[Transaction]:
    """Try CSV first, then free-text.  Returns [] when nothing parses."""
    has_delim = any(d in text for d in (",", ";", "\t"))
    looks_csv = has_delim and text.count("\n") >= 1

    if looks_csv:
        txns = parse_csv(text)
        if txns:
            return txns

    return parse_freetext(text)
