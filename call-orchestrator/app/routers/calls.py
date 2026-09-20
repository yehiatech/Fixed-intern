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
from twilio.rest import Client as TwilioClient

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


@router.post("/trigger", response_model=CallTriggerResponse, status_code=202)
def trigger_call(payload: CallTriggerRequest) -> CallTriggerResponse:
    if not payload.customer_phone.startswith("+"):
        raise APIError(
            status_code=400,
            error="invalid_phone_number",
            message="The phone number format is invalid. Must start with +",
            call_id=payload.call_id,
        )

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
    twilio_sid: str

    if is_dev_mode() or not settings.public_base_url:
        # Local/dev testing: no real Twilio call placed. Use
        # /voice/incoming/{call_id} yourself via curl to simulate it.
        twilio_sid = f"CA{uuid.uuid4().hex}"
        logger.info(
            "DEV_MODE: trigger_call accepted (no real call placed) call_id=%s org_id=%s",
            payload.call_id,
            payload.org_id,
        )
    else:
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        call = client.calls.create(
            url=f"{settings.public_base_url}/voice/incoming/{payload.call_id}",
            to=payload.customer_phone,
            from_=settings.twilio_phone_number,
        )
        twilio_sid = call.sid
        logger.info("Real Twilio call placed for call_id=%s sid=%s", payload.call_id, twilio_sid)

    return CallTriggerResponse(
        status="accepted",
        call_id=payload.call_id,
        twilio_sid=twilio_sid,
        message="Call initiated",
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
