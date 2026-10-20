"""Bill splitting: even / uneven split + settlement minimisation."""

from typing import List, Dict


class SplitCalculator:
    # ── splits ─────────────────────────────────────────────────────────

    @staticmethod
    def even_split(amount: float, people: List[str]) -> List[Dict]:
        if not people:
            return []
        share = round(amount / len(people), 2)
        # First person absorbs rounding remainder
        first = round(amount - share * (len(people) - 1), 2)
        return [{"name": p, "amount": first if i == 0 else share}
                for i, p in enumerate(people)]

    @staticmethod
    def uneven_split(amount: float, weights: Dict[str, float]) -> List[Dict]:
        total_w = sum(weights.values())
        if total_w == 0:
            return []
        return [
            {"name": p, "amount": round(amount * w / total_w, 2)}
            for p, w in weights.items()
        ]

    # ── settlement minimisation ────────────────────────────────────────

    @staticmethod
    def minimize_settlements(balances: Dict[str, float]) -> List[Dict]:
        """Given {name: net_balance} (positive = owed, negative = owes),
        return the minimal list of transfers to settle everyone."""
        debtors = sorted(
            ((k, v) for k, v in balances.items() if v < -0.005),
            key=lambda x: x[1],
        )
        creditors = sorted(
            ((k, v) for k, v in balances.items() if v > 0.005),
            key=lambda x: x[1],
            reverse=True,
        )

        settlements: List[Dict] = []
        i = j = 0
        while i < len(debtors) and j < len(creditors):
            debtor, debt = debtors[i]
            creditor, credit = creditors[j]
            amt = round(min(abs(debt), credit), 2)
            if amt > 0:
                settlements.append({"from": debtor, "to": creditor, "amount": amt})
            debtors[i] = (debtor, debt + amt)
            creditors[j] = (creditor, credit - amt)
            if abs(debtors[i][1]) < 0.005:
                i += 1
            if creditors[j][1] < 0.005:
                j += 1

        return settlements

    # ── formatting ─────────────────────────────────────────────────────

    @staticmethod
    def format_split(description: str, total: float, shares: List[Dict]) -> str:
        lines = [f"═══ Split: {description} ═══", ""]
        lines.append(f"💵 Total: ${total:,.2f}")
        lines.append(f"👥 Split {len(shares)} ways:")
        lines.append("")
        for s in shares:
            lines.append(f"  {s['name']:<15} ${s['amount']:>8,.2f}")
        per = shares[0]["amount"] if shares else 0
        lines += ["", f"💡 Each person owes ${per:,.2f}"]
        return "\n".join(lines)
