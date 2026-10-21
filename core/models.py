"""Shared data models for BudgetBuddy."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class Transaction:
    date: datetime
    amount: float  # signed: negative = expense, positive = income
    description: str
    merchant: str = ""
    category: str = "other"
    currency: str = "USD"
    is_ambiguous_date: bool = False
    raw_line: str = ""

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "amount": self.amount,
            "description": self.description,
            "merchant": self.merchant,
            "category": self.category,
            "currency": self.currency,
            "is_ambiguous_date": self.is_ambiguous_date,
            "raw_line": self.raw_line,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        return cls(
            date=datetime.fromisoformat(d["date"]),
            amount=d["amount"],
            description=d["description"],
            merchant=d.get("merchant", ""),
            category=d.get("category", "other"),
            currency=d.get("currency", "USD"),
            is_ambiguous_date=d.get("is_ambiguous_date", False),
            raw_line=d.get("raw_line", ""),
        )


@dataclass
class Goal:
    target_amount: float
    deadline: datetime
    description: str = ""
    monthly_target: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "target_amount": self.target_amount,
            "deadline": self.deadline.isoformat(),
            "description": self.description,
            "monthly_target": self.monthly_target,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Goal":
        return cls(
            target_amount=d["target_amount"],
            deadline=datetime.fromisoformat(d["deadline"]),
            description=d.get("description", ""),
            monthly_target=d.get("monthly_target", 0.0),
            created_at=datetime.fromisoformat(d["created_at"]),
        )


@dataclass
class SplitEntry:
    name: str
    amount: float
    paid: bool = False


@dataclass
class SplitBill:
    description: str
    total: float
    entries: List[SplitEntry] = field(default_factory=list)
    settlements: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "total": self.total,
            "entries": [{"name": e.name, "amount": e.amount, "paid": e.paid} for e in self.entries],
            "settlements": self.settlements,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class PaymentRequest:
    id: str
    amount: float
    currency: str
    description: str
    status: str = "pending"  # pending | paid | cancelled | expired
    created_at: datetime = field(default_factory=datetime.now)
    paid_at: Optional[datetime] = None
    # ── Agent Payment Protocol fields ──
    session_id: str = ""          # which conversation asked for Pro
    buyer: str = ""               # agent address expected to pay
    rail: str = ""                # payment_method (bb_commit/stripe/fet_direct)
    reference: str = ""           # unique id echoed back in the commit
    challenge: str = ""           # nonce the buyer signs to commit
    transaction_id: str = ""      # rail-specific proof of payment
    expires_at: Optional[datetime] = None
    recipient: str = ""           # where funds should be sent

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "amount": self.amount,
            "currency": self.currency,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "session_id": self.session_id,
            "buyer": self.buyer,
            "rail": self.rail,
            "reference": self.reference,
            "challenge": self.challenge,
            "transaction_id": self.transaction_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "recipient": self.recipient,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaymentRequest":
        return cls(
            id=d["id"],
            amount=d["amount"],
            currency=d["currency"],
            description=d["description"],
            status=d.get("status", "pending"),
            created_at=datetime.fromisoformat(d["created_at"]),
            paid_at=datetime.fromisoformat(d["paid_at"]) if d.get("paid_at") else None,
            session_id=d.get("session_id", ""),
            buyer=d.get("buyer", ""),
            rail=d.get("rail", ""),
            reference=d.get("reference", ""),
            challenge=d.get("challenge", ""),
            transaction_id=d.get("transaction_id", ""),
            expires_at=(
                datetime.fromisoformat(d["expires_at"]) if d.get("expires_at") else None
            ),
            recipient=d.get("recipient", ""),
        )
