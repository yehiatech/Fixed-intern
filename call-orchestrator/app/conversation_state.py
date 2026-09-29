"""Call state: same API as before (voice.py / calls.py need no changes),
but every change is now also saved to a SQLite file, so results survive
server restarts and the admin can still see them afterwards.

get_state() still returns a mutable dict; assigning any top-level key
(state["ended"] = True, state["resolution"] = "...") autosaves.
"""
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("CALLS_DB_PATH", "calls.db")
_lock = threading.RLock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute(
    """CREATE TABLE IF NOT EXISTS call_state (
        call_id    TEXT PRIMARY KEY,
        org_id     TEXT,
        ended      INTEGER NOT NULL DEFAULT 0,
        resolution TEXT,
        data       TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )"""
)
_conn.commit()


class _State(dict):
    """dict that saves itself whenever a top-level key is assigned."""

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        _save(self)


def _save(state: dict) -> None:
    try:
        with _lock:
            _conn.execute(
                "INSERT INTO call_state (call_id, org_id, ended, resolution, data, updated_at) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(call_id) DO UPDATE SET "
                "org_id=excluded.org_id, ended=excluded.ended, resolution=excluded.resolution, "
                "data=excluded.data, updated_at=excluded.updated_at",
                (
                    state["call_id"], state.get("org_id"), int(bool(state.get("ended"))),
                    state.get("resolution"), json.dumps(state, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            _conn.commit()
    except Exception:
        # never break a live call because saving failed
        logger.exception("Failed to persist call %s", state.get("call_id"))


def _load_all() -> dict[str, _State]:
    with _lock:
        rows = _conn.execute("SELECT data FROM call_state").fetchall()
    return {(d := json.loads(r[0]))["call_id"]: _State(d) for r in rows}


_calls: dict[str, _State] = _load_all()
logger.info("Loaded %d saved calls from %s", len(_calls), DB_PATH)


def exists(call_id: str) -> bool:
    with _lock:
        return call_id in _calls


def init_call(call_id: str, customer_name: str, org_id: str, ticket_id: str,
              customer_phone: str = "") -> dict[str, Any]:
    state = _State({
        "call_id": call_id, "customer_name": customer_name, "customer_phone": customer_phone,
        "org_id": org_id, "ticket_id": ticket_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "messages": [], "transcript": [], "no_input_retries": 0,
        "ended": False, "transferred": False,
        "resolution": None, "sentiment": None, "tools_used": [],
    })
    with _lock:
        _calls[call_id] = state
    _save(state)
    return state


def get_state(call_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        return _calls.get(call_id)


def all_calls() -> list[dict[str, Any]]:
    with _lock:
        return list(_calls.values())


def append_transcript(call_id: str, role: str, text: str) -> None:
    state = get_state(call_id)
    if state is None:
        logger.warning("append_transcript: unknown call_id=%s", call_id)
        return
    state["transcript"].append({"role": role, "text": text})
    _save(state)


def clear_call(call_id: str) -> None:
    with _lock:
        _calls.pop(call_id, None)
        _conn.execute("DELETE FROM call_state WHERE call_id=?", (call_id,))
        _conn.commit()
