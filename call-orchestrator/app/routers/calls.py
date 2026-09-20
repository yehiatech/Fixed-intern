"""
POST /calls/trigger — placeholder for T-11 (skeleton stage only).

Real behavior (Bedrock tool calling, Twilio outbound call, retry logic,
writing to call_logs) is built in T-12 and T-13. At this stage the route
must exist and respond, but do nothing structural yet.
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])


class CallTriggerRequest(BaseModel):
    """
    Shape this to match the API contract with Person 1's bridge script
    (T-07b) once that's agreed. ticket_id and customer_id are the two
    fields we already know we'll need, from the call_logs schema.
    """
    ticket_id: str
    customer_id: str
    organization_id: str


class CallTriggerResponse(BaseModel):
    message: str


@router.post("/trigger", response_model=CallTriggerResponse)
def trigger_call(payload: CallTriggerRequest) -> CallTriggerResponse:
    logger.info(
        "trigger_call called for ticket_id=%s customer_id=%s (not implemented yet)",
        payload.ticket_id,
        payload.customer_id,
    )
    return CallTriggerResponse(message="not implemented")
