"""
T-12: in-memory conversation state per call_id. Holds the Bedrock message
history (needed for multi-turn converse() calls), the transcript, and the
outcome fields /calls/result needs to answer per the API contract.

Replaced by real call_logs DB reads/writes in T-13 — the shape of this
dict is deliberately close to the call_logs columns so that swap is easy.
"""
from typing import Any
import threading

_calls: dict[str, dict[str, Any]] = {}
_state_lock = threading.Lock()

def _cleanup_old_calls():
    # Naive cleanup: if we exceed 1000 calls, remove the oldest 200
    if len(_calls) > 1000:
        keys_to_delete = list(_calls.keys())[:200]
        for k in keys_to_delete:
            del _calls[k]

def init_call(call_id: str, customer_name: str, org_id: str, ticket_id: str) -> dict[str, Any]:
    with _state_lock:
        _cleanup_old_calls()
        state = {
            "customer_name": customer_name,
            "org_id": org_id,
            "ticket_id": ticket_id,
            "messages": [],       # Bedrock converse() message history
            "transcript": "",     # human-readable transcript for /calls/result
            "tools_used": [],
            "resolution": None,
            "sentiment": None,
            "ended": False,
            "transferred": False,
            "no_input_retries": 0,
        }
        _calls[call_id] = state
        return state


def get_state(call_id: str) -> dict[str, Any] | None:
    # Read-only access doesn't strictly need a lock for dict lookup due to GIL, 
    # but mutations to the returned state should be locked.
    return _calls.get(call_id)


def exists(call_id: str) -> bool:
    return call_id in _calls


def append_transcript(call_id: str, speaker: str, text: str) -> None:
    with _state_lock:
        state = _calls.get(call_id)
        if state is not None:
            state["transcript"] += f"{speaker}: {text}\n"

def update_state_safe(call_id: str, resolution: str = None, sentiment: str = None, tools_used: list = None, ended: bool = None) -> bool:
    with _state_lock:
        state = _calls.get(call_id)
        if not state:
            return False
        
        if resolution is not None:
            state["resolution"] = resolution
        if sentiment is not None:
            state["sentiment"] = sentiment
        if tools_used is not None:
            for t in tools_used:
                if t not in state["tools_used"]:
                    state["tools_used"].append(t)
        if ended is not None:
            state["ended"] = ended
            
        return True
