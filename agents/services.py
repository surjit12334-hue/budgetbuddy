"""Shared service singletons used by every agent.

All agents run in the same process (Bureau), so one instance of each
service is enough.  The SessionStore points at the same SQLite file
regardless of which agent accesses it.
"""

from core.state import SessionStore
from core.llm import LLMClient
from core.categorizer import Categorizer
from core.analyzer import Analyzer
from core.coach import Coach
from core.goal import GoalCalculator
from core.splitter import SplitCalculator
from core.payments import PaymentManager
from core.cards import CardBuilder

# ── singletons ─────────────────────────────────────────────────────────

store = SessionStore()
llm = LLMClient()
categorizer = Categorizer(llm)
analyzer = Analyzer()
coach = Coach(llm)
goal_calc = GoalCalculator()
splitter = SplitCalculator()
payments = PaymentManager()
cards = CardBuilder()
