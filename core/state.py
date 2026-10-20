"""SQLite-backed session store with 24 h TTL purge."""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path
from .models import Transaction


class SessionStore:
    def __init__(self, db_path: str = None, ttl_hours: int = None):
        self.db_path = db_path or os.environ.get("SESSION_DB", "budgetbuddy.db")
        ttl = ttl_hours or int(os.environ.get("SESSION_TTL_HOURS", "24"))
        self.ttl = timedelta(hours=ttl)
        self._init_db()

    # ── private ────────────────────────────────────────────────────────

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id         TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data       TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.commit()

    def _purge_expired(self):
        cutoff = (datetime.now() - self.ttl).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
            conn.commit()

    # ── public API ──────────────────────────────────────────────────────

    def create_session(self, session_id: str) -> Dict:
        self._purge_expired()
        now = datetime.now().isoformat()
        data: Dict = {"created_at": now, "transactions": [], "history": []}
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, created_at, updated_at, data)"
                " VALUES (?, ?, ?, ?)",
                (session_id, now, now, json.dumps(data)),
            )
            conn.commit()
        return data

    def get_session(self, session_id: str) -> Optional[Dict]:
        self._purge_expired()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def get_or_create(self, session_id: str) -> Dict:
        return self.get_session(session_id) or self.create_session(session_id)

    def update_session(self, session_id: str, data: Dict):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(data), now, session_id),
            )
            conn.commit()

    # ── convenience helpers ─────────────────────────────────────────────

    def save_transactions(self, session_id: str, transactions: List[Transaction]):
        session = self.get_or_create(session_id)
        session["transactions"] = [t.to_dict() for t in transactions]
        self.update_session(session_id, session)

    def load_transactions(self, session_id: str) -> List[Transaction]:
        session = self.get_session(session_id)
        if session and session.get("transactions"):
            return [Transaction.from_dict(d) for d in session["transactions"]]
        return []

    def add_message(self, session_id: str, role: str, text: str):
        session = self.get_or_create(session_id)
        session.setdefault("history", []).append(
            {"role": role, "text": text, "ts": datetime.now().isoformat()}
        )
        self.update_session(session_id, session)

    def purge_expired_sessions(self):
        self._purge_expired()

    def purge_all(self):
        """Wipe every session (for testing /reset)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions")
            conn.commit()
