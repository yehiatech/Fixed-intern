"""
The two Vonage webhooks that drive the conversation — Vonage's
equivalent of Twilio's TwiML webhooks, but the response format is NCCO
(a JSON array of actions) instead of XML, and there's no <Gather>/<Say>
tags — the "input" action (with type=["speech"]) does what Gather did,
and "talk" does what Say did.

/voice/answer/{call_id}  — Vonage's answer_url, hit once the call connects.
/voice/events/{call_id}  — the input action's eventUrl, hit with the
                            recognized speech every time the customer talks.

TTS: Vonage's "talk" action with language="arb" (Amazon Polly's Arabic
Standard voice under the hood — same voice/language pairing we verified
works for the Twilio version).
STT: Vonage's built-in ASR (the "input" action's speech.language param),
supports "ar-EG" (Egyptian Arabic) natively — no separate STT call needed.
"""
import logging

from fastapi import APIRouter, Request

from app.bedrock_client import run_agent_turn
from app.config import get_settings
from app.conversation_state import append_transcript, get_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

MAX_NO_INPUT_RETRIES = 2


def _talk_and_listen_ncco(call_id: str, prompt_text: str) -> list[dict]:
    """Speak prompt_text, then listen for Arabic (Egyptian) speech,
    with barge-in enabled so the customer can interrupt."""
    settings = get_settings()
    event_url = f"{settings.public_base_url}/voice/events/{call_id}"
    return [
        {"action": "talk", "text": prompt_text, "language": "arb", "bargeIn": True},
        {
            "action": "input",
            "type": ["speech"],
            "eventUrl": [event_url],
            "eventMethod": "POST",
            "speech": {
                "language": "ar-EG",
                "endOnSilence": 1.5,
                "startTimeout": 10,
            },
        },
    ]


@router.post("/answer/{call_id}")
def voice_answer(call_id: str) -> list[dict]:
    """Vonage's answer_url — hit once the customer's phone connects.
    Must return an NCCO (list of action dicts), not TwiML."""
    state = get_state(call_id)
    if state is None:
        # Defensive fallback — shouldn't happen if /calls/trigger ran first.
        return [{"action": "talk", "text": "عذراً، حدث خطأ. مع السلامة.", "language": "arb"}]

    greeting = (
        f"مرحباً {state['customer_name']}، معاك المساعد الذكي من خدمة العملاء. "
        "هل تم حل المشكلة اللي كنت تواصلت بخصوصها قبل كده؟"
    )
    state["messages"].append({"role": "assistant", "content": [{"text": greeting}]})
    append_transcript(call_id, "assistant", greeting)

    return _talk_and_listen_ncco(call_id, greeting)


@router.post("/events/{call_id}")
async def voice_events(call_id: str, request: Request) -> list[dict]:
    """Vonage's eventUrl for the input action — hit with the ASR result
    (or a timeout) every time the customer speaks."""
    settings = get_settings()
    state = get_state(call_id)
    if state is None:
        return [{"action": "talk", "text": "عذراً، حدث خطأ. مع السلامة.", "language": "arb"}]

    body = await request.json()
    speech = body.get("speech") or {}
    results = speech.get("results") or []
    speech_text = results[0]["text"] if results else ""

    if not speech_text.strip():
        state["no_input_retries"] += 1
        if state["no_input_retries"] > MAX_NO_INPUT_RETRIES:
            state["ended"] = True
            state["resolution"] = state["resolution"] or "no_response_ended"
            return [
                {"action": "talk", "text": "مش قادر أسمعك، هقفل المكالمة دلوقتي. مع السلامة.", "language": "arb"}
            ]
        return _talk_and_listen_ncco(call_id, "عذراً، ممكن تعيد تاني؟")

    append_transcript(call_id, "customer", speech_text)
    state["messages"].append({"role": "user", "content": [{"text": speech_text}]})

    text_to_speak, action = run_agent_turn(call_id, state["messages"])
    state["messages"].append({"role": "assistant", "content": [{"text": text_to_speak}]})
    append_transcript(call_id, "assistant", text_to_speak)

    if action == "end_call":
        state["ended"] = True
        # No further "input" action → Vonage ends the call once this talk finishes.
        return [{"action": "talk", "text": text_to_speak, "language": "arb"}]

    if action == "transfer":
        state["ended"] = True
        state["transferred"] = True
        ncco = [{"action": "talk", "text": text_to_speak, "language": "arb"}]
        if settings.transfer_agent_number:
            ncco.append(
                {
                    "action": "connect",
                    "endpoint": [{"type": "phone", "number": settings.transfer_agent_number}],
                }
            )
        else:
            logger.warning("call_id=%s: transfer requested but no transfer_agent_number configured", call_id)
        return ncco

    return _talk_and_listen_ncco(call_id, text_to_speak)
