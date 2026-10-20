"""Merchant normalisation + keyword categoriser with LLM fallback."""

import re
from typing import Optional, Dict, List

from .models import Transaction
from .llm import LLMClient

# ──────────────────────── category keyword map ─────────────────────────

CATEGORY_MAP: Dict[str, List[str]] = {
    "groceries": [
        "grocery", "groceries", "supermarket", "walmart", "target",
        "kroger", "safeway", "whole foods", "wholefoods", "aldi",
        "trader joe", "costco", "sam's club", "food market", "provisions",
        "food town", "piggly", "heb", "publix", "wegmans", "fresh market",
    ],
    "dining": [
        "restaurant", "cafe", "coffee", "starbucks", "mcdonald", "burger",
        "pizza", "taco", "chipotle", "subway", "dunkin", "doordash",
        "uber eats", "grubhub", "takeout", "lunch", "dinner", "breakfast",
        "bar", "pub", "brewery", "diner", "grill", "bistro", "eatery",
        "peet", "panera", "sweetgreen", "chick-fil-a", "wendy", "kfc",
        "dominos", "papa john", "olive garden", "applebee", "chili",
    ],
    "transport": [
        "uber", "lyft", "taxi", "gas", "fuel", "shell", "chevron",
        "exxon", "parking", "transit", "metro", "bus ", "train",
        "airline", "delta", "united airlines", "southwest", "flight",
        "amtrak", "bart ", "mbta", "cta ", "toll", "carwash", "auto repair",
    ],
    "utilities": [
        "electric", "power company", "water department", "water bill",
        "gas company", "utility", "sewer", "trash", "internet",
        "comcast", "verizon", "at&t", "t-mobile", "phone bill",
        "mobile", "broadband", "wifi", "spectrum", "cox ", "xfinity",
        "energy", "natural gas",
    ],
    "rent": [
        "rent", "lease", "apartment", "housing", "mortgage", "hoa",
        "landlord", "property management",
    ],
    "entertainment": [
        "netflix", "spotify", "hulu", "disney", "hbo", "youtube premium",
        "youtube music", "apple music", "twitch", "steam", "epic games",
        "game", "movie", "cinema", "theater", "theatre", "concert",
        "amusement", "paramount", "peacock", "apple tv", "soundcloud",
        "pandora", "tidal", "audible", "adobe", "creative cloud",
    ],
    "shopping": [
        "amazon", "ebay", "etsy", "best buy", "apple store", "nike",
        "adidas", "zara", "h&m", "uniqlo", "clothing", "shoes",
        "electronics", "ikea", "wayfair", "target", "walmart",
        "macys", "nordstrom", "sephora", "ulta", "dick sporting",
    ],
    "health": [
        "pharmacy", "cvs", "walgreens", "rite aid", "doctor", "hospital",
        "clinic", "dental", "dentist", "vision", "optometry", "gym",
        "fitness", "health", "medical", "insurance", "urgent care",
        "planet fitness", "classpass", "peloton", "equinox",
    ],
    "education": [
        "tuition", "school", "university", "college", "course",
        "udemy", "coursera", "textbook", "education", "bookstore",
        "kindle", "student loan", "chegg", "skillshare",
    ],
    "subscriptions": [
        "subscription", "monthly fee", "annual fee", "membership",
        "prime video", "patreon", "premium", "pro plan", "plus plan",
        "onlyfans",
    ],
    "income": [
        "salary", "paycheck", "deposit", "refund", "interest",
        "dividend", "freelance", "invoice", "payment received",
        "cashback", "reward", "wages", "bonus", "payroll",
    ],
    "transfers": [
        "transfer", "send money", "venmo", "paypal", "zelle",
        "cash app", "wire", "ach", "savings transfer", "cashapp",
    ],
}

# ──────────────────────── merchant normalisation ──────────────────────

MERCHANT_CANON: Dict[str, str] = {
    "MCDONALD'S": "McDonald's",
    "MCDONALDS": "McDonald's",
    "STARBUCKS": "Starbucks",
    "NETFLIX": "Netflix",
    "SPOTIFY": "Spotify",
    "AMAZON": "Amazon",
    "AMZN": "Amazon",
    "AMAZON PRIME": "Amazon Prime",
    "WALMART": "Walmart",
    "WAL-MART": "Walmart",
    "WHOLE FOODS": "Whole Foods",
    "WHOLEFOODS": "Whole Foods",
    "TRADER JOE": "Trader Joe's",
    "TRADER JOE'S": "Trader Joe's",
    "UBER EATS": "Uber Eats",
    "UBER": "Uber",
    "LYFT": "Lyft",
    "DOORDASH": "DoorDash",
    "ADOBE": "Adobe",
    "ADOBE CREATIVE CLOUD": "Adobe Creative Cloud",
    "CHIPOTLE": "Chipotle",
    "COMCAST": "Comcast",
    "XFINITY": "Comcast",
    "T-MOBILE": "T-Mobile",
    "PLANET FITNESS": "Planet Fitness",
    "PEETS": "Peet's Coffee",
    "PEET'S": "Peet's Coffee",
}


def normalize_merchant(desc: str) -> str:
    """Turn a raw description into a clean merchant name."""
    upper = desc.upper().strip()

    # Direct lookup
    for pattern, canonical in MERCHANT_CANON.items():
        if pattern in upper:
            return canonical

    # Strip leading/trailing noise
    merchant = re.sub(r"#\d+", "", desc).strip()
    merchant = re.split(r"\s+[-–—]\s+|\s{2,}|\t", merchant)[0].strip()
    merchant = re.sub(
        r"\s*(Inc|LLC|Corp|Ltd|Co|Company)\.?\s*$", "", merchant, flags=re.IGNORECASE
    ).strip()

    if merchant.isupper():
        merchant = merchant.title()

    return merchant or desc.strip()


# ──────────────────────── categoriser ──────────────────────────────────


class Categorizer:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    # ── public ──

    def categorize(self, txn: Transaction) -> str:
        """Set txn.category and return the category string."""
        desc_lower = txn.description.lower()
        merchant_lower = (txn.merchant or "").lower()

        # Income wins when amount > 0
        if txn.amount > 0:
            for kw in CATEGORY_MAP["income"]:
                if kw in desc_lower or kw in merchant_lower:
                    txn.category = "income"
                    return txn.category

        # Keyword scan (skip income bucket — handled above)
        for cat, keywords in CATEGORY_MAP.items():
            if cat == "income":
                continue
            for kw in keywords:
                if kw in desc_lower or kw in merchant_lower:
                    txn.category = cat
                    return txn.category

        # LLM fallback for unknown merchants
        if self.llm and self.llm.available:
            cat = self._llm_categorize(txn)
            if cat:
                txn.category = cat
                return txn.category

        txn.category = "other"
        return txn.category

    def categorize_all(self, transactions: List[Transaction]) -> List[Transaction]:
        for txn in transactions:
            if not txn.merchant:
                txn.merchant = normalize_merchant(txn.description)
            self.categorize(txn)
        return transactions

    # ── LLM fallback ──

    def _llm_categorize(self, txn: Transaction) -> Optional[str]:
        valid = set(CATEGORY_MAP.keys()) | {"other"}
        prompt = (
            "Categorise this bank transaction into exactly one of: "
            + ", ".join(sorted(valid))
            + f"\n\nTransaction: {txn.description}\nAmount: {txn.amount}\n\n"
            "Return only the category name, nothing else."
        )
        raw = self.llm.generate(prompt)
        if raw:
            cat = raw.strip().lower().strip('"\'.,`')
            if cat in valid:
                return cat
        return None
