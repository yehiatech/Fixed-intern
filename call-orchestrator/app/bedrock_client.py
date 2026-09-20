"""
T-12: runs one full "agent turn" — send the conversation to Bedrock,
execute any tool it calls, send the result back, repeat until Bedrock
returns plain text to speak. That text plus whether a terminal tool
fired is what routers/voice.py needs to build the next TwiML response.

DEV_MODE: if no AWS credentials are configured, falls back to a simple
keyword-based fake responder so you can test the whole call flow locally
without needing real Bedrock model access enabled on your AWS account.
Real accounts often need Bedrock model access requested/approved first —
this lets T-12's plumbing be tested before that's sorted out.
"""
import logging

import boto3

from app.config import get_settings
from app.tools import TERMINAL_TOOLS, TOOL_CONFIG, execute_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "إنت مساعد ذكي بتكلم عملاء بعد ما اتواصلوا مع خدمة العملاء قبل كده. "
    "مهمتك تتأكد هل المشكلة اتحلت ولا لأ. اتكلم باللهجة المصرية، بجمل قصيرة وواضحة. "
    "استخدم الأدوات المتاحة لتسجيل نتيجة المكالمة بدل ما تحاول تفهم الرد بنفسك."
)


def is_dev_mode() -> bool:
    settings = get_settings()
    return not (settings.aws_access_key_id and settings.aws_secret_access_key)


def _get_bedrock_client():
    settings = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def run_agent_turn(call_id: str, messages: list[dict]) -> tuple[str, str]:
    """
    messages: full Bedrock-format message history, ending with the
    customer's latest turn already appended.

    Returns (text_to_speak, action) where action is one of:
    "continue" (keep gathering), "end_call", or "transfer".
    """
    if is_dev_mode():
        return _fake_agent_turn(call_id, messages)
    return _real_agent_turn(call_id, messages)


def _real_agent_turn(call_id: str, messages: list[dict]) -> tuple[str, str]:
    settings = get_settings()
    client = _get_bedrock_client()
    action = "continue"

    for _ in range(4):  # safety cap on tool-call round trips per turn
        response = client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            toolConfig=TOOL_CONFIG,
        )
        assistant_message = response["output"]["message"]
        messages.append(assistant_message)

        tool_uses = [b["toolUse"] for b in assistant_message["content"] if "toolUse" in b]
        if not tool_uses:
            text = "".join(b.get("text", "") for b in assistant_message["content"])
            return text, action

        tool_result_blocks = []
        for tool_use in tool_uses:
            name = tool_use["name"]
            result = execute_tool(call_id, name, tool_use.get("input", {}))
            if name in TERMINAL_TOOLS:
                action = "end_call" if name == "end_call" else "transfer"
            tool_result_blocks.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"json": result}],
                    }
                }
            )
        messages.append({"role": "user", "content": tool_result_blocks})

    logger.warning("call_id=%s: hit tool-call round trip cap without final text", call_id)
    return "شكراً لوقتك، مع السلامة.", "end_call"


def _fake_agent_turn(call_id: str, messages: list[dict]) -> tuple[str, str]:
    """DEV_MODE ONLY. Simple keyword matching so the full webhook/TwiML
    flow can be tested without real AWS credentials configured."""
    last_user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            texts = [b.get("text", "") for b in msg["content"] if "text" in b]
            if texts:
                last_user_text = texts[0]
                break

    text_lower = last_user_text.strip()

    if any(w in text_lower for w in ["موظف", "حد يكلمني", "مشرف"]):
        execute_tool(call_id, "transfer_to_agent", {"ticket_id": call_id, "reason": "customer requested agent"})
        return "تمام، هحولك لموظف خدمة العملاء دلوقتي.", "transfer"

    # Check farewell/end-call phrases BEFORE the generic negative check —
    # "لا شكراً" (no thanks) contains "لا " but means "I'm done", not "it's
    # not resolved". Order matters for this simple keyword matcher.
    if any(w in text_lower for w in ["لا شكراً", "خلاص", "مفيش حاجة", "سلام"]):
        execute_tool(call_id, "end_call", {"goodbye_message": "شكراً لوقتك، مع السلامة."})
        return "شكراً لوقتك، مع السلامة.", "end_call"

    if any(w in text_lower for w in ["لأ", "لا ", "مش اتحلت", "لسه موجودة"]):
        execute_tool(call_id, "record_complaint", {"ticket_id": call_id, "complaint_text": last_user_text})
        return "آسف لسماع كده، سجلت المشكلة وهيتم التواصل معاك قريب. حاجة تانية؟", "continue"

    if any(w in text_lower for w in ["نعم", "أيوه", "اتحلت", "تمام"]):
        execute_tool(call_id, "mark_ticket_resolved", {"ticket_id": call_id, "resolution_note": last_user_text})
        return "الحمد لله، شكراً لتأكيدك. حاجة تانية تحب تسأل عنها؟", "continue"

    execute_tool(call_id, "ask_followup_question", {"question_text": "..."})
    return "عذراً، ممكن توضح أكتر؟ هل المشكلة اتحلت ولا لسه؟", "continue"
