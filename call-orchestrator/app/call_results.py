"""
Persists the outcome of each test call (resolved / not_resolved /
unclear) so an admin can check later which customers still need a
follow-up call. Uses SQLite (a single file, no extra service needed)
so results survive server restarts — unlike conversation_state.py's
in-memory dict.
"""
import sqlite3
from datetime import datetime, timezone

DB_PATH = "call_results.sqlite3"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS call_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_phone TEXT NOT NULL,
            decision TEXT NOT NULL,
            speech_text TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def save_result(customer_phone: str, decision: str, speech_text: str) -> None:
    """decision should be one of: resolved, not_resolved, unclear."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO call_results (customer_phone, decision, speech_text, created_at) VALUES (?, ?, ?, ?)",
        (customer_phone, decision, speech_text, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def get_all_results() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT customer_phone, decision, speech_text, created_at FROM call_results ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [
        {"customer_phone": r[0], "decision": r[1], "speech_text": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_results_for_phone(customer_phone: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT customer_phone, decision, speech_text, created_at FROM call_results "
        "WHERE customer_phone = ? ORDER BY id DESC",
        (customer_phone,),
    ).fetchall()
    conn.close()
    return [
        {"customer_phone": r[0], "decision": r[1], "speech_text": r[2], "created_at": r[3]}
        for r in rows
    ]
