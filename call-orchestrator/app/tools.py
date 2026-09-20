"""
T-12: the 5 tools Claude (via Bedrock converse + toolConfig) can invoke
during an outbound call. TOOL_CONFIG is passed straight into the
converse() call; execute_tool() runs the matching Python side effect
once Bedrock decides to call one.
"""
import logging

from app.conversation_state import get_state

logger = logging.getLogger(__name__)

# Tools that end the conversation — once one of these fires, the webhook
# hangs up (or dials an agent) after speaking the final response.
TERMINAL_TOOLS = {"transfer_to_agent", "end_call"}

TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "mark_ticket_resolved",
                "description": "استخدم هذه الأداة عندما يؤكد العميل أن مشكلته السابقة تم حلها بالكامل.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticket_id": {"type": "string", "description": "رقم التذكرة"},
                            "resolution_note": {"type": "string", "description": "ملخص قصير لتأكيد العميل"},
                        },
                        "required": ["ticket_id", "resolution_note"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "record_complaint",
                "description": "استخدم هذه الأداة عندما يقول العميل إن المشكلة لسه موجودة أو يصف مشكلة جديدة.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticket_id": {"type": "string", "description": "رقم التذكرة"},
                            "complaint_text": {"type": "string", "description": "وصف الشكوى بكلام العميل"},
                        },
                        "required": ["ticket_id", "complaint_text"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "ask_followup_question",
                "description": "استخدم هذه الأداة لما رد العميل يكون غير واضح، وتحتاج توضيح قبل ما تكمل.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "question_text": {"type": "string", "description": "السؤال التوضيحي اللي هيتقال للعميل"},
                        },
                        "required": ["question_text"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "transfer_to_agent",
                "description": "استخدم هذه الأداة لما العميل يطلب صراحة يتكلم مع موظف حقيقي.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticket_id": {"type": "string", "description": "رقم التذكرة"},
                            "reason": {"type": "string", "description": "سبب التحويل"},
                        },
                        "required": ["ticket_id", "reason"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "end_call",
                "description": "استخدم هذه الأداة لما تكون المحادثة خلصت طبيعي وتحب تقفل المكالمة بلطف.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "goodbye_message": {"type": "string", "description": "رسالة الوداع اللي هتتقال للعميل"},
                        },
                        "required": ["goodbye_message"],
                    }
                },
            }
        },
    ]
}


def execute_tool(call_id: str, tool_name: str, tool_input: dict) -> dict:
    """
    Runs the side effect for one tool call and returns a small result dict
    that gets sent back to Bedrock as a toolResult, plus is used locally to
    know whether to hang up / transfer once the turn is done.
    """
    state = get_state(call_id)
    state["tools_used"].append(tool_name)

    if tool_name == "mark_ticket_resolved":
        state["resolution"] = "resolved_first_call"
        state["sentiment"] = "positive"
        logger.info("call_id=%s: ticket marked resolved (%s)", call_id, tool_input.get("resolution_note"))
        return {"result": "ok", "note": "Ticket marked resolved."}

    if tool_name == "record_complaint":
        state["resolution"] = "unresolved_complaint"
        state["sentiment"] = "frustrated"
        state["complaint_text"] = tool_input.get("complaint_text", "")
        logger.info("call_id=%s: complaint recorded: %s", call_id, state["complaint_text"])
        return {"result": "ok", "note": "Complaint recorded."}

    if tool_name == "ask_followup_question":
        # No state change needed — the question itself is spoken by Bedrock's
        # own response text, this tool just signals "ask, don't conclude yet".
        return {"result": "ok", "note": "Follow-up question will be asked."}

    if tool_name == "transfer_to_agent":
        state["resolution"] = "transferred_to_agent"
        state["sentiment"] = state.get("sentiment") or "neutral"
        state["transfer_reason"] = tool_input.get("reason", "")
        logger.info("call_id=%s: transferring to agent, reason=%s", call_id, state["transfer_reason"])
        return {"result": "ok", "note": "Transferring call to a human agent."}

    if tool_name == "end_call":
        state["resolution"] = state.get("resolution") or "call_ended"
        state["sentiment"] = state.get("sentiment") or "neutral"
        logger.info("call_id=%s: ending call", call_id)
        return {"result": "ok", "note": "Call will end after this message."}

    logger.warning("call_id=%s: unknown tool_name=%s", call_id, tool_name)
    return {"result": "error", "note": f"Unknown tool: {tool_name}"}
