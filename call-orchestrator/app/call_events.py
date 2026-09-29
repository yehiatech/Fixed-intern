"""Vonage call-status events (the event_url that calls.py already sends).

Without this, calls nobody answers - or that the customer hangs up
halfway - never get marked as finished, so they never show up as
unresolved and nobody knows to call them back.
"""
import logging

from fastapi import APIRouter, Request

from app.conversation_state import get_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

NOT_REACHED = {"busy", "cancelled", "failed", "rejected", "timeout", "unanswered"}


@router.post("/call-events/{call_id}")
async def call_events(call_id: str, request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    status = body.get("status")
    state = get_state(call_id)
    logger.info("call=%s vonage status=%s", call_id, status)

    if state is None or state["ended"]:
        return {"ok": True}

    if status in NOT_REACHED:
        state["resolution"] = "no_answer"       # customer never picked up
        state["ended"] = True
    elif status == "completed":
        # line closed but nothing marked it finished -> customer hung up mid-call
        state["resolution"] = state["resolution"] or "hung_up"
        state["ended"] = True
    return {"ok": True}
