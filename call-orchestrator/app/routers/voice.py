"""
T-12: the two Twilio webhooks that drive the actual voice conversation.

/voice/incoming/{call_id}   — first hit, once the customer answers.
/voice/handle-response/{call_id} — hit every time Gather captures speech.

TTS is Amazon Polly's Arabic neural voice "Zeina", used via Twilio's
built-in <Say voice="Polly.Zeina"> — no separate Polly API call needed,
Twilio renders it directly (per the architecture decision in the prompt).
STT is Twilio's own <Gather input="speech" language="ar-EG">, not a
separate transcription call.
"""
import logging

from fastapi import APIRouter, Form, Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.bedrock_client import run_agent_turn
from app.config import get_settings
from app.conversation_state import append_transcript, get_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

MAX_NO_INPUT_RETRIES = 2


def _gather_response(call_id: str, prompt_text: str) -> str:
    """Build a <Gather> TwiML block that speaks prompt_text, listens for
    Arabic speech with barge-in enabled, and falls back gracefully if the
    customer says nothing."""
    settings = get_settings()
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        language="ar-EG",
        bargeIn=True,
        speech_timeout="auto",
        action=f"/voice/handle-response/{call_id}",
        method="POST",
    )
    gather.say(prompt_text, voice=settings.polly_voice, language="ar-EG")
    response.append(gather)
    # If Gather times out with no speech at all, Twilio falls through to here.
    response.redirect(f"/voice/handle-response/{call_id}?no_input=true", method="POST")
    return str(response)


@router.post("/incoming/{call_id}")
def voice_incoming(call_id: str) -> Response:
    settings = get_settings()
    state = get_state(call_id)
    if state is None:
        # Defensive fallback — shouldn't happen if /calls/trigger ran first.
        response = VoiceResponse()
        response.say("عذراً، حدث خطأ. مع السلامة.", voice=settings.polly_voice, language="ar-EG")
        response.hangup()
        return Response(content=str(response), media_type="text/xml")

    greeting = (
        f"مرحباً {state['customer_name']}، معاك المساعد الذكي من خدمة العملاء. "
        "هل تم حل المشكلة اللي كنت تواصلت بخصوصها قبل كده؟"
    )
    state["messages"].append({"role": "assistant", "content": [{"text": greeting}]})
    append_transcript(call_id, "assistant", greeting)

    return Response(content=_gather_response(call_id, greeting), media_type="text/xml")


@router.post("/handle-response/{call_id}")
def voice_handle_response(
    call_id: str,
    SpeechResult: str = Form(default=""),
    no_input: bool = False,
) -> Response:
    settings = get_settings()
    state = get_state(call_id)
    if state is None:
        response = VoiceResponse()
        response.say("عذراً، حدث خطأ. مع السلامة.", voice=settings.polly_voice, language="ar-EG")
        response.hangup()
        return Response(content=str(response), media_type="text/xml")

    if no_input or not SpeechResult.strip():
        state["no_input_retries"] += 1
        if state["no_input_retries"] > MAX_NO_INPUT_RETRIES:
            state["ended"] = True
            state["resolution"] = state["resolution"] or "no_response_ended"
            response = VoiceResponse()
            response.say("مش قادر أسمعك، هقفل المكالمة دلوقتي. مع السلامة.", voice=settings.polly_voice, language="ar-EG")
            response.hangup()
            return Response(content=str(response), media_type="text/xml")

        return Response(
            content=_gather_response(call_id, "عذراً، ممكن تعيد تاني؟"),
            media_type="text/xml",
        )

    # Customer said something — feed it into the Bedrock tool-calling loop.
    append_transcript(call_id, "customer", SpeechResult)
    state["messages"].append({"role": "user", "content": [{"text": SpeechResult}]})

    text_to_speak, action = run_agent_turn(call_id, state["messages"])
    state["messages"].append({"role": "assistant", "content": [{"text": text_to_speak}]})
    append_transcript(call_id, "assistant", text_to_speak)

    response = VoiceResponse()
    response.say(text_to_speak, voice=settings.polly_voice, language="ar-EG")

    if action == "end_call":
        state["ended"] = True
        response.hangup()
    elif action == "transfer":
        state["ended"] = True
        state["transferred"] = True
        if settings.transfer_agent_number:
            response.dial(settings.transfer_agent_number)
        else:
            logger.warning("call_id=%s: transfer requested but no transfer_agent_number configured", call_id)
            response.hangup()
    else:
        response.append(
            Gather(
                input="speech",
                language="ar-EG",
                bargeIn=True,
                speech_timeout="auto",
                action=f"/voice/handle-response/{call_id}",
                method="POST",
            )
        )
        response.redirect(f"/voice/handle-response/{call_id}?no_input=true", method="POST")

    return Response(content=str(response), media_type="text/xml")
