import logging
import os
import re

from dotenv import load_dotenv
from fastapi import APIRouter, Request

load_dotenv()

PUBLIC_URL = os.getenv("PUBLIC_URL", "")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

RESOLVED_WORDS = {
    "تم", "اتحل", "اتحلت", "ايوه", "أيوه",
    "نعم", "تمام", "خلصت", "اه", "أه", "ايوة"
}

NOT_RESOLVED_WORDS = {
    "لا", "لأ", "مش", "لسه", "لسة", "معملتش"
}


def _decide(speech_text: str) -> str:
    words = set(re.findall(r"[\u0600-\u06FF]+", speech_text))

    if words & NOT_RESOLVED_WORDS:
        return "not_resolved"

    if words & RESOLVED_WORDS:
        return "resolved"

    return "unclear"


@router.post("/speech")
async def speech_webhook(request: Request) -> list[dict]:
    body = await request.json()

    logger.info("Vonage speech webhook body: %s", body)

    speech = body.get("speech") or {}
    results = speech.get("results") or []

    speech_text = results[0]["text"] if results else ""

    logger.info("Customer said: %s", speech_text)

    decision = _decide(speech_text)

    if decision == "resolved":
        reply = "تمام، شكراً جداً لوقتك. مع السلامة."
        return [
            {
                "action": "talk",
                "text": reply,
                "language": "ar"
            }
        ]

    elif decision == "not_resolved":
        reply = "حاضر، هخلي حد من فريقنا يتواصل معاك في أقرب وقت."
        return [
            {
                "action": "talk",
                "text": reply,
                "language": "ar"
            },
            {
                "action": "input",
                "type": ["speech"],
                "speech": {
                    "provider": "google",
                    "providerOptions": {
                        "language_code": "ar-EG"
                    },
                    "endOnSilence": 2,
                    "maxDuration": 30
                },
                "eventUrl": [
                    f"{PUBLIC_URL}/webhooks/speech"
                ],
                "eventMethod": "POST"
            }
        ]

    else:
        reply = "عذراً، مقدرتش أفهم ردك. ممكن توضحيلي أكتر؟"
        return [
            {
                "action": "talk",
                "text": reply,
                "language": "ar"
            },
            {
                "action": "input",
                "type": ["speech"],
                "speech": {
                    "provider": "google",
                    "providerOptions": {
                        "language_code": "ar-EG"
                    },
                    "endOnSilence": 2,
                    "maxDuration": 30
                },
                "eventUrl": [
                    f"{PUBLIC_URL}/webhooks/speech"
                ],
                "eventMethod": "POST"
            }
        ]