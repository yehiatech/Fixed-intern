"""
T-12: in-memory conversation state per call_id. Holds the Bedrock message
history (needed for multi-turn converse() calls), the transcript, and the
outcome fields /calls/result needs to answer per the API contract.

Replaced by real call_logs DB reads/writes in T-13 — the shape of this
dict is deliberately close to the call_logs columns so that swap is easy.
"""
from typing import Any

_calls: dict[str, dict[str, Any]] = {}


def init_call(call_id: str, customer_name: str, org_id: str, ticket_id: str) -> dict[str, Any]:
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
    return _calls.get(call_id)


def exists(call_id: str) -> bool:
    return call_id in _calls


def append_transcript(call_id: str, speaker: str, text: str) -> None:
    state = _calls.get(call_id)
    if state is not None:
        state["transcript"] += f"{speaker}: {text}\n"
