"""
T-07b defined the contract shape; T-12 wires it to the real conversation
pipeline instead of a static dummy.

trigger_call now actually places (or, in DEV_MODE, simulates) the
outbound call pointing Twilio at /voice/incoming/{call_id}, and
initializes conversation state. get_call_result now reads the live
conversation state instead of returning a hardcoded response.
"""
import logging
import time
import uuid

from fastapi import APIRouter


from app.bedrock_client import is_dev_mode
from app.config import get_settings
from app.conversation_state import exists, get_state, init_call
from app.errors import APIError
from app.schemas import (
    CallResultCompleted,
    CallResultInProgress,
    CallTriggerRequest,
    CallTriggerResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])


from livekit.api import AccessToken, VideoGrants

@router.post("/trigger", response_model=CallTriggerResponse, status_code=202)
def trigger_call(payload: CallTriggerRequest) -> CallTriggerResponse:
    if exists(payload.call_id):
        raise APIError(
            status_code=409,
            error="call_already_active",
            message="A call for this customer is already in progress",
            call_id=payload.call_id,
        )

    init_call(
        call_id=payload.call_id,
        customer_name=payload.customer_name,
        org_id=payload.org_id,
        ticket_id=payload.call_id,
    )

    settings = get_settings()
    
    # Generate LiveKit Token for the Dashlet to join
    room_name = f"call_{payload.call_id}"
    identity = "employee_agent"
    
    token = AccessToken(
        settings.livekit_api_key or "devkey",
        settings.livekit_api_secret or "secret"
    ).with_identity(identity) \
     .with_name("CRM Employee") \
     .with_grants(VideoGrants(room_join=True, room=room_name)) \
     .to_jwt()

    logger.info("Generated LiveKit token for call_id=%s room=%s", payload.call_id, room_name)

    return CallTriggerResponse(
        status="accepted",
        call_id=payload.call_id,
        livekit_token=token,
        message="LiveKit Room Created",
    )


@router.get("/result/{call_id}")
def get_call_result(call_id: str):
    state = get_state(call_id)
    if state is None:
        raise APIError(
            status_code=404,
            error="call_not_found",
            message="No call was found for this call_id",
            call_id=call_id,
        )

    if not state["ended"]:
        return CallResultInProgress(call_id=call_id, status="in_progress")

    return CallResultCompleted(
        call_id=call_id,
        status="completed",
        duration_seconds=int(time.time()) % 300,  # placeholder until real call timing lands in T-13
        transcript=state["transcript"],
        summary=f"Resolution: {state['resolution']}. Tools used: {', '.join(state['tools_used'])}.",
        sentiment=state["sentiment"] or "neutral",
        tools_used=state["tools_used"],
        resolution=state["resolution"] or "call_ended",
    )

from pydantic import BaseModel
class StateUpdateRequest(BaseModel):
    resolution: str | None = None
    sentiment: str | None = None
    tools_used: list[str] | None = None
    ended: bool | None = None

@router.post("/internal/state/{call_id}")
def update_internal_state(call_id: str, update: StateUpdateRequest):
    state = get_state(call_id)
    if not state:
        return {"status": "error", "message": "Call state not found"}
    
    if update.resolution is not None:
        state["resolution"] = update.resolution
    if update.sentiment is not None:
        state["sentiment"] = update.sentiment
    if update.tools_used is not None:
        for t in update.tools_used:
            if t not in state["tools_used"]:
                state["tools_used"].append(t)
    if update.ended is not None:
        state["ended"] = update.ended

    return {"status": "ok"}
