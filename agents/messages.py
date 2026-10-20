"""Typed message models for agent-to-agent communication.

Every request carries a unique request_id so the host can
correlate async responses (pending-future pattern).
"""

from uagents import Model


# ── Ingest ─────────────────────────────────────────────────────────────

class IngestRequest(Model):
    request_id: str
    session_id: str
    text: str


class IngestResponse(Model):
    request_id: str
    reply: str
    txn_count: int


# ── Analyst ────────────────────────────────────────────────────────────

class AnalysisRequest(Model):
    request_id: str
    session_id: str


class AnalysisResponse(Model):
    request_id: str
    report: str
    insights: str


# ── Coach ──────────────────────────────────────────────────────────────

class CoachRequest(Model):
    request_id: str
    session_id: str


class CoachResponse(Model):
    request_id: str
    message: str


# ── Goal ───────────────────────────────────────────────────────────────

class GoalRequest(Model):
    request_id: str
    session_id: str
    text: str


class GoalResponse(Model):
    request_id: str
    plan: str


# ── Splitter ───────────────────────────────────────────────────────────

class SplitRequest(Model):
    request_id: str
    text: str


class SplitResponse(Model):
    request_id: str
    result: str


# ── External Query / Response (host ↔ world) ──────────────────────────

class Query(Model):
    session_id: str
    text: str


class Response(Model):
    reply: str


# ── Health (for preflight / uptime monitoring) ────────────────────────

class HealthResponse(Model):
    status: str
    agents: dict
    session_ttl_hours: int
