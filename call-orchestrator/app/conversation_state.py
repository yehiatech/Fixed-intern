"""In-memory conversation state, shared by app/routers/calls.py and
app/routers/voice.py within this single FastAPI process."""
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_calls: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def exists(call_id: str) -> bool:
    with _lock:
        return call_id in _calls


def init_call(call_id: str, customer_name: str, org_id: str, ticket_id: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        "call_id": call_id,
        "customer_name": customer_name,
        "org_id": org_id,
        "ticket_id": ticket_id,
        "messages": [],
        "transcript": [],
        "no_input_retries": 0,
        "ended": False,
        "transferred": False,
        "resolution": None,
        "sentiment": None,
        "tools_used": [],
    }
    with _lock:
        _calls[call_id] = state
    logger.info("call_id=%s: state initialized (ticket_id=%s)", call_id, ticket_id)
    return state


def get_state(call_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        return _calls.get(call_id)


def append_transcript(call_id: str, role: str, text: str) -> None:
    state = get_state(call_id)
    if state is None:
        logger.warning("append_transcript: unknown call_id=%s", call_id)
        return
    state["transcript"].append({"role": role, "text": text})


def clear_call(call_id: str) -> None:
    with _lock:
        _calls.pop(call_id, None)