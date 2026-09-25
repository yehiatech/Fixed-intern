"""
trigger_call places a real outbound PSTN call through Vonage's Voice
API (voice.create_call), pointing Vonage's answer_url at
/voice/answer/{call_id}. get_call_result reads the same
conversation_state dict that app/routers/voice.py's webhooks write to
directly — back to a single process, no internal state-sync endpoint
needed (that was only necessary for the LiveKit split-process setup).
"""
import logging
import time
import uuid

from fastapi import APIRouter
from vonage import Auth, Vonage
from vonage_voice import CreateCallRequest, PhoneEndpoint, ToPhone

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


def _is_dev_mode() -> bool:
    settings = get_settings()
    return not (settings.vonage_application_id and settings.vonage_private_key_path and settings.public_base_url)


@router.post("/trigger", response_model=CallTriggerResponse, status_code=202)
def trigger_call(payload: CallTriggerRequest) -> CallTriggerResponse:
    if not payload.customer_phone.startswith("+"):
        raise APIError(
            status_code=400,
            error="invalid_phone_number",
            message="The phone number format is invalid. Must start with +",
            call_id=payload.call_id,
        )

    init_call(
        call_id=payload.call_id,
        customer_name=payload.customer_name,
        org_id=payload.org_id,
        ticket_id=payload.call_id,
    )

    settings = get_settings()

    if _is_dev_mode():
        # No real Vonage application configured yet — return a fake uuid
        # so the endpoint is still testable (contract shape, 400/409
        # handling) without a Vonage account. Hit
        # POST /voice/answer/{call_id} yourself to simulate the call
        # connecting, same as we did for the Twilio version.
        vonage_call_uuid = f"DEV_MODE_FAKE_{uuid.uuid4().hex}"
        logger.info("DEV_MODE: trigger_call accepted (no real call placed) call_id=%s", payload.call_id)
    else:
        client = Vonage(
            Auth(
                application_id=settings.vonage_application_id,
                private_key=settings.vonage_private_key_path,
            )
        )
        # Vonage numbers are E.164 without the leading "+".
        to_number = payload.customer_phone.lstrip("+")
        from_number = settings.vonage_number

        response = client.voice.create_call(
    CreateCallRequest(
        to=[ToPhone(number=to_number)],
        from_=PhoneEndpoint(number=from_number),

        # Called when the customer answers the call
        answer_url=[
            f"{settings.public_base_url}/voice/answer/{payload.call_id}"
        ],
        answer_method="POST",

        # Called by Vonage with call status events
        event_url=[
            f"{settings.public_base_url}/voice/call-events/{payload.call_id}"
        ],
        event_method="POST",
    )
)
        vonage_call_uuid = response.uuid
        logger.info("Real Vonage call placed: uuid=%s call_id=%s", vonage_call_uuid, payload.call_id)

    return CallTriggerResponse(
        status="accepted",
        call_id=payload.call_id,
        vonage_call_uuid=vonage_call_uuid,
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
