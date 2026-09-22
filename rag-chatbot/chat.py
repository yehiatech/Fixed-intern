# -*- coding: utf-8 -*-
"""
T-17: /chat endpoint logic.

1. Topic Guard  -> ALLOWED / BLOCKED (keyword-based, no Bedrock call).
2. Direct RAG   -> try a direct knowledge-base search first; if the top
                   match already clears the citation threshold, answer
                   from it without spending a Bedrock generation call.
3. Tool-calling -> otherwise fall back to Bedrock `converse` + 4 tools;
                   the model decides which tool(s) to call.
4. Citation     -> similarity >= 0.75 = KB-grounded; else labeled fallback.
5. Logging      -> every interaction saved to chat_interactions.

Notes: check_order_status is a stub (no orders system yet).
lookup_ticket calls the real EspoCRM API.
"""
import os
import json
import time
import uuid
import boto3
import requests

from db import get_connection
from ingestion import search_chunks

CHAT_MODEL_ID = os.getenv("CHAT_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
CITATION_THRESHOLD = 0.75
MAX_TOOL_ITERATIONS = 5

HARMFUL_KEYWORDS = [
    "hack", "exploit", "malware", "فيروس", "اختراق", "قنبلة", "bomb",
    "weapon", "سلاح", "self harm", "suicide", "انتحار", "أذى نفسي",
    "مخدرات", "drugs", "قتل", "kill",
]

OFFTOPIC_KEYWORDS = [
    "weather", "الطقس", "الجو", "football", "كرة القدم", "مباراة",
    "recipe", "وصفة طبخ", "طبخ", "horoscope", "أبراج", "joke", "نكتة",
    "movie", "فيلم", "مسلسل", "song", "أغنية", "سياسة", "politics",
]


def topic_guard(query: str) -> tuple[str, str]:
    lowered = query.lower()
    for word in HARMFUL_KEYWORDS:
        if word in lowered:
            return "BLOCKED", "harmful_content"
    for word in OFFTOPIC_KEYWORDS:
        if word in lowered:
            return "BLOCKED", "off_topic"
    return "ALLOWED", "ok"


REFUSAL_MESSAGE = (
    "عذرًا، هذا السؤال خارج نطاق المساعدة التي أقدمها. "
    "أنا مخصص للإجابة على استفسارات متعلقة بخدمات وسياسات الشركة فقط."
)


def _tool_search_knowledge_base(tool_input: dict, organization_id: str) -> dict:
    query = tool_input.get("query", "")
    results = search_chunks(query, organization_id, top_k=3)
    return {"results": results}


def _tool_lookup_ticket(tool_input: dict, organization_id: str) -> dict:
    ticket_id = tool_input["ticket_id"]
    base_url = os.getenv("ESPOCRM_SITE_URL", "").rstrip("/")
    api_key = os.getenv("ESPOCRM_API_KEY", "")

    if not base_url or not api_key:
        return {"found": False, "message": "لم يتم إعداد الاتصال بنظام EspoCRM بعد."}

    try:
        response = requests.get(
            f"{base_url}/api/v1/CFollowUpCall/{ticket_id}",
            headers={"X-Api-Key": api_key},
            timeout=8,
        )
    except requests.RequestException as e:
        return {"found": False, "message": f"فشل الاتصال بنظام EspoCRM: {e}"}

    if response.status_code == 404:
        return {"found": False, "message": f"لم يتم العثور على تذكرة بالرقم {ticket_id}."}
    if not response.ok:
        return {"found": False, "message": f"استجاب نظام EspoCRM بخطأ HTTP {response.status_code}."}

    data = response.json()
    return {"found": True, "ticket_id": ticket_id, "raw": data}


def _tool_check_order_status(tool_input: dict, organization_id: str) -> dict:
    return {"available": False, "message": "خدمة تتبع الطلبات غير متاحة حاليًا."}


def _tool_escalate_to_human(tool_input: dict, organization_id: str) -> dict:
    return {"escalated": True, "message": "تم تصعيد هذه المحادثة لمراجعة أحد موظفي الدعم البشري."}


TOOL_FUNCTIONS = {
    "search_knowledge_base": _tool_search_knowledge_base,
    "lookup_ticket": _tool_lookup_ticket,
    "check_order_status": _tool_check_order_status,
    "escalate_to_human": _tool_escalate_to_human,
}

TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "search_knowledge_base",
                "description": "Search the company knowledge base for relevant policy/document chunks.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query."}
                        },
                        "required": ["query"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "lookup_ticket",
                "description": "Fetch a support ticket/call log by its ticket ID.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticket_id": {"type": "string", "description": "The ticket ID to look up."}
                        },
                        "required": ["ticket_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "check_order_status",
                "description": "Check the delivery/processing status of a customer order.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The order ID to check."}
                        },
                        "required": ["order_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "escalate_to_human",
                "description": "Flag the current conversation for review by a human agent.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Why this needs human review."}
                        },
                        "required": ["reason"],
                    }
                },
            }
        },
    ]
}

SYSTEM_PROMPT = (
    "أنت مساعد خدمة عملاء يجيب فقط على الأسئلة المتعلقة بخدمات الشركة وسياساتها "
    "وتذاكر الدعم والطلبات. يجب أن تكون جميع إجاباتك باللغة العربية دائمًا، "
    "بغض النظر عن لغة السؤال. "
    "\n\n"
    "قاعدة إلزامية: يجب عليك استخدام أداة search_knowledge_base في أول رسالة "
    "لأي سؤال يتعلق بسياسة الشركة أو خدماتها، حتى لو كنت تعتقد أنك تعرف الإجابة. "
    "لا تجب أبدًا من معرفتك العامة مباشرة - ابحث في قاعدة المعرفة أولاً دائمًا. "
    "بعد الحصول على نتائج البحث، اذكر رقم الصفحة (page number) التي وردت منها المعلومة. "
    "استخدم lookup_ticket أو check_order_status أو escalate_to_human عند الحاجة. "
    "إذا لم تجد قاعدة المعرفة إجابة ذات صلة بعد البحث الفعلي، وضّح ذلك بصراحة."
)


def _bedrock_client():
    return boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))


def _run_tool_loop(query: str, organization_id: str) -> tuple[str, float | None, bool, dict | None]:
    client = _bedrock_client()
    messages = [{"role": "user", "content": [{"text": query}]}]

    best_kb_similarity = None
    used_kb_tool = False
    best_kb_result = None

    for i in range(MAX_TOOL_ITERATIONS):
        tool_config = TOOL_CONFIG
        if i == 0:
            tool_config = {**TOOL_CONFIG, "toolChoice": {"any": {}}}

        response = client.converse(
            modelId=CHAT_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            toolConfig=tool_config,
        )
        output_message = response["output"]["message"]
        messages.append(output_message)

        stop_reason = response.get("stopReason")
        if stop_reason != "tool_use":
            text_parts = [b["text"] for b in output_message["content"] if "text" in b]
            return " ".join(text_parts).strip(), best_kb_similarity, used_kb_tool, best_kb_result

        tool_result_blocks = []
        for block in output_message["content"]:
            if "toolUse" not in block:
                continue
            tool_use = block["toolUse"]
            name = tool_use["name"]
            tool_input = tool_use.get("input", {})
            fn = TOOL_FUNCTIONS.get(name)

            if fn is None:
                result = {"error": f"Unknown tool: {name}"}
            elif name == "search_knowledge_base":
                result = fn({"query": query}, organization_id)
            else:
                result = fn(tool_input, organization_id)

            if name == "search_knowledge_base":
                used_kb_tool = True
                kb_results = result.get("results", [])
                if kb_results:
                    best = max(kb_results, key=lambda r: r["similarity"])
                    if best_kb_similarity is None or best["similarity"] > best_kb_similarity:
                        best_kb_similarity = best["similarity"]
                        best_kb_result = best

            tool_result_blocks.append({
                "toolResult": {
                    "toolUseId": tool_use["toolUseId"],
                    "content": [{"json": result}],
                }
            })

        messages.append({"role": "user", "content": tool_result_blocks})

    return (
        "عذرًا، لم أتمكن من إكمال الإجابة في الوقت المناسب.",
        best_kb_similarity,
        used_kb_tool,
        best_kb_result,
    )


def _log_interaction(organization_id, user_id, query_text, answer_text,
                      topic_guard_status, source_type, similarity_score, latency_ms):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_interactions
                        (id, organization_id, user_id, query_text, answer_text,
                         topic_guard_status, source_type, similarity_score, latency_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), organization_id, user_id, query_text, answer_text,
                        topic_guard_status, source_type, similarity_score, latency_ms,
                    ),
                )
    finally:
        conn.close()


def handle_chat(query: str, organization_id: str, user_id: str | None = None) -> dict:
    start = time.time()

    status, reason = topic_guard(query)
    if status == "BLOCKED":
        latency_ms = int((time.time() - start) * 1000)
        _log_interaction(
            organization_id, user_id, query, REFUSAL_MESSAGE,
            topic_guard_status="BLOCKED", source_type=None,
            similarity_score=None, latency_ms=latency_ms,
        )
        return {
            "answer": REFUSAL_MESSAGE,
            "topic_guard_status": "BLOCKED",
            "source_type": None,
            "similarity_score": None,
        }

    # Try a direct KB search first (cheap, no Bedrock generation call).
    # If it already clears the threshold, answer from it directly.
    try:
        direct_results = search_chunks(query, organization_id, top_k=3)
    except Exception:
        direct_results = []

    best_kb_result = None
    best_similarity = None
    used_kb_tool = False
    answer = None

    if direct_results:
        top = max(direct_results, key=lambda r: r["similarity"])
        if top["similarity"] >= CITATION_THRESHOLD:
            answer = top["chunk_text"]
            best_similarity = top["similarity"]
            best_kb_result = top
            used_kb_tool = True

    if answer is None:
        answer, best_similarity, used_kb_tool, best_kb_result = _run_tool_loop(query, organization_id)

    if (used_kb_tool and best_similarity is not None
            and best_similarity >= CITATION_THRESHOLD and best_kb_result):
        source_type = "kb_match"
        answer = f"{answer}\n\nالمصدر: {best_kb_result['source_file']} - الصفحة {best_kb_result['page_number']}"
    else:
        source_type = "fallback_general"
        answer = f"[إجابة من الذكاء الاصطناعي، وليست من قاعدة المعرفة] {answer}"

    latency_ms = int((time.time() - start) * 1000)
    _log_interaction(
        organization_id, user_id, query, answer,
        topic_guard_status="ALLOWED", source_type=source_type,
        similarity_score=best_similarity, latency_ms=latency_ms,
    )

    return {
        "answer": answer,
        "topic_guard_status": "ALLOWED",
        "source_type": source_type,
        "similarity_score": best_similarity,
    }