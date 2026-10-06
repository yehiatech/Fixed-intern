# -*- coding: utf-8 -*-
"""
T-17: /chat endpoint logic.

1. Topic Guard  -> ALLOWED / BLOCKED (keyword-based, no Bedrock call).
2. Direct RAG   -> try a direct knowledge-base search first; if the top
                   match already clears the citation threshold, answer
                   from it without spending a Bedrock generation call.
3. Tool-calling -> otherwise fall back to Bedrock `converse` + 5 tools;
                   the model decides which tool(s) to call.
4. Citation     -> similarity >= 0.75 = KB-grounded; else labeled fallback.
5. Logging      -> every interaction saved to chat_interactions.

Notes: check_order_status is a stub (no orders system yet).
lookup_ticket calls the real EspoCRM API.
query_structured_data answers counting/filtering questions over
support_tickets by generating read-only SQL (see sql_query.py) - it does
NOT have access to the users table or any other org's rows (enforced by
Postgres row-level security, not by this file).
"""
import os
import json
import time
import uuid
import boto3
import requests

from db import get_connection
from ingestion import search_chunks
from ticket_service import create_ticket_record, TicketError
try:  # Text-to-SQL is optional: if it cannot load, the chatbot still works without it
    from sql.sql_query import run_structured_query
except Exception as _sql_err:
    try:
        from sql_query import run_structured_query
    except Exception:
        print(f"[chat] Text-to-SQL disabled (could not load): {_sql_err}")
        run_structured_query = None
from personas import build_system_prompt, resolve_persona, HEADER, PERSONA_GUARD


CHAT_MODEL_ID = os.getenv("CHAT_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
CITATION_THRESHOLD = 0.35
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


def _tool_query_structured_data(tool_input: dict, organization_id: str) -> dict:
    """Natural-language question -> read-only SQL over support_tickets.
    organization_id here always comes from the authenticated caller
    (handle_chat's parameter), never from the model's tool_input, so the
    model cannot ask for a different tenant's data through this path."""
    question = tool_input.get("question", "")
    if run_structured_query is None:
        return {"status": "error", "answer": None,
                "message": "عذرًا، تعذر الوصول إلى البيانات حاليًا. برجاء المحاولة لاحقًا."}
    return run_structured_query(question, organization_id, get_connection)


def _messages_to_transcript(messages: list) -> list[dict]:
    """Plain-text copy of the conversation (tool calls/results dropped) for the ticket."""
    transcript = []
    for m in messages:
        text = " ".join(b["text"] for b in m.get("content", []) if isinstance(b, dict) and "text" in b).strip()
        if text:
            transcript.append({"role": m.get("role", "user"), "text": text})
    return transcript


def _tool_create_ticket(tool_input: dict, organization_id: str, transcript: list | None = None) -> dict:
    name = tool_input.get("customer_name", "Unknown")
    phone = tool_input.get("phone_number", "Unknown")
    desc = tool_input.get("issue_description", "Unknown")

    # Force the AI to ask the user if they hallucinated a generic response
    generic_words = ["unknown", "escalation", "none", "n/a", "غير معروف", "طلب التحدث لموظف", "التحدث مع الدعم", "لا يوجد", "لم يحدد", "مجهول"]
    is_generic = any(w in desc.lower() for w in generic_words)
    if is_generic or len(desc) < 4:
        return {
            "error": "TICKET CREATION FAILED. You provided a missing or placeholder issue_description. You MUST explicitly ask the user 'What is the problem/issue you are facing?' and wait for their response before trying again."
        }

    # Save the ticket in the same database the dashboards read from.
    try:
        created = create_ticket_record(
            organization_id=organization_id,
            customer_name=name,
            phone_number=phone,
            issue_description=desc,
            ai_transcript=transcript,
            source="chatbot",
        )
    except TicketError as e:
        return {
            "error": f"TICKET NOT SAVED ({e.message}). Do NOT tell the customer a ticket was created. "
                     "Apologize briefly and tell them the request could not be registered right now."
        }
    except Exception:
        return {
            "error": "TICKET NOT SAVED (database error). Do NOT tell the customer a ticket was created. "
                     "Apologize briefly and tell them the request could not be registered right now."
        }

    ticket_id = created["id"]
    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": f"Successfully created ticket {ticket_id} for {name} ({phone}).",
    }




TOOL_FUNCTIONS = {
    "search_knowledge_base": _tool_search_knowledge_base,
    "lookup_ticket": _tool_lookup_ticket,
    "check_order_status": _tool_check_order_status,
    "create_ticket": _tool_create_ticket,
    "query_structured_data": _tool_query_structured_data,
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
                "name": "create_ticket",
                "description": "Create a new support ticket. You MUST explicitly collect the issue_description from the user. Do NOT invent, guess, or use placeholders for the issue.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "customer_name": {"type": "string"},
                            "phone_number": {"type": "string"},
                            "issue_description": {"type": "string"}
                        },
                        "required": ["customer_name", "phone_number", "issue_description"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "query_structured_data",
                "description": "Answer questions that need counting, filtering, or listing support tickets (e.g. 'كام تذكرة مفتوحة؟', 'اعرض التذاكر اللي لسه معلقة', 'how many tickets today'). Do NOT use this for policy/document questions - use search_knowledge_base for those instead.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "السؤال كما طرحه المستخدم، بنفس لغته."}
                        },
                        "required": ["question"],
                    }
                },
            }
        },

    ]
}

SYSTEM_PROMPT = """أنت مساعد ذكي لخدمة العملاء. هدفك هو تقديم إجابات استباقية وسريعة للعملاء.

تعليمات الشخصية والأسلوب (Persona & Tone):
1. النبرة: كن ودوداً ومهنياً.
2. التنسيق: اجعل إجاباتك قصيرة ومريحة للعين. استخدم النقط (Bullet points) للخطوات، وقم بتمييز الكلمات المهمة بخط عريض (**Bold**).
3. الرموز التعبيرية: استخدم الرموز التعبيرية بشكل نادر جداً أو لا تستخدمها.
4. الشفافية: أنت ذكاء اصطناعي، لا تتظاهر بأنك إنسان.

قواعد الاسترجاع من المعلومات والتصعيد (RAG & Escalation):
1. ابحث دائماً في قاعدة المعرفة باستخدام الأداة (search_knowledge_base) قبل الإجابة على أي سؤال يخص الشركة أو السياسات.
2. لا تخترع (Hallucinate) أي معلومات من خارج النصوص المسترجعة أبداً.
3. عند تقديم معلومات من قاعدة المعرفة، حافظ على دقة المعلومات المرجعية.
4. **هام جداً للتصعيد وفتح التذاكر**: عندما يطلب المستخدم التحدث إلى موظف بشري أو عندما تقرر أنه بحاجة لدعم بشري، يجب عليك جمع المعلومات التالية أولاً:
   - الاسم
   - رقم الهاتف
   - وصف المشكلة
   **لا تقم بإنشاء التذكرة أبداً إذا كانت أي من هذه المعلومات مفقودة.** استمر في سؤاله بلباقة عن المعلومات الناقصة. بمجرد توفر المعلومات الثلاثة، استخدم أداة (create_ticket) لإنشاء التذكرة فوراً، ثم أكد له أنه سيتم التواصل معه.

استخدم lookup_ticket أو check_order_status أو create_ticket عند الحاجة.
استخدم query_structured_data فقط للأسئلة التي تحتاج عد أو تصفية أو سرد للتذاكر (مثل "كام تذكرة مفتوحة؟")."""


SQL_TOOL_NAME = "query_structured_data"
SQL_PROMPT_HINT = ("\nاستخدم query_structured_data فقط للأسئلة التي تحتاج عد أو تصفية أو سرد للتذاكر "
                   "(مثل \"كام تذكرة مفتوحة؟\").")


def _sql_enabled() -> bool:
    """The SQL tool is on only if its module loaded AND it is configured
    (OPENAI_API_KEY + SQL_ALLOWED_TABLES). Otherwise the chatbot behaves exactly
    as it did before the SQL feature existed."""
    return (run_structured_query is not None
            and bool(os.getenv("OPENAI_API_KEY"))
            and bool(os.getenv("SQL_ALLOWED_TABLES")))


def _active_tool_config() -> dict:
    if _sql_enabled():
        return TOOL_CONFIG
    return {**TOOL_CONFIG,
            "tools": [t for t in TOOL_CONFIG["tools"] if t["toolSpec"]["name"] != SQL_TOOL_NAME]}


def _bedrock_client():
    region = os.getenv("AWS_REGION")
    if not region:
        region = "us-east-1"
    return boto3.client("bedrock-runtime", region_name=region)


def _run_tool_loop(query: str, organization_id: str, history: list = None,
                   persona_id: str | None = None) -> tuple[str, float | None, bool, dict | None]:
    if history is None:
        history = []
    client = _bedrock_client()
    messages = history + [{"role": "user", "content": [{"text": query}]}]
    persona_text, _ = resolve_persona(organization_id, persona_id)
    system_prompt = build_system_prompt(persona_text) + (SQL_PROMPT_HINT if _sql_enabled() else "")

    best_kb_similarity = None
    used_kb_tool = False
    best_kb_result = None

    for i in range(MAX_TOOL_ITERATIONS):
        tool_config = _active_tool_config()
        if i == 0:
            tool_config = {**tool_config, "toolChoice": {"any": {}}}

        response = client.converse(
            modelId=CHAT_MODEL_ID,
            system=[{"text": system_prompt}],
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
            elif name == "create_ticket":
                result = fn(tool_input, organization_id, transcript=_messages_to_transcript(messages))
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
    interaction_id = str(uuid.uuid4())
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
                        interaction_id, organization_id, user_id, query_text, answer_text,
                        topic_guard_status, source_type, similarity_score, latency_ms,
                    ),
                )
        return interaction_id
    finally:
        conn.close()


def _apply_persona(chunk_text: str, query: str, persona_text: str) -> str:
    """Re-word a knowledge-base passage in the org's persona. Facts come only
    from the passage. Any failure returns the passage unchanged."""
    try:
        response = _bedrock_client().converse(
            modelId=CHAT_MODEL_ID,
            system=[{"text": HEADER + persona_text + PERSONA_GUARD +
                     "أعد صياغة النص المرجعي التالي كإجابة على سؤال العميل بالأسلوب المطلوب، "
                     "واعتمد فقط على المعلومات الموجودة في النص دون إضافة أي معلومة جديدة."}],
            messages=[{"role": "user", "content": [{"text": f"سؤال العميل: {query}\n\nالنص المرجعي:\n{chunk_text}"}]}],
        )
        parts = [b["text"] for b in response["output"]["message"]["content"] if "text" in b]
        rephrased = " ".join(parts).strip()
        return rephrased or chunk_text
    except Exception:
        return chunk_text


def handle_chat(query: str, organization_id: str, user_id: str | None = None, history: list = None,
                persona_id: str | None = None) -> dict:
    if history is None:
        history = []
    start = time.time()

    status, reason = topic_guard(query)
    if status == "BLOCKED":
        latency_ms = int((time.time() - start) * 1000)
        interaction_id = _log_interaction(
            organization_id, user_id, query, REFUSAL_MESSAGE,
            topic_guard_status="BLOCKED", source_type=None,
            similarity_score=None, latency_ms=latency_ms,
        )
        return {
            "answer": REFUSAL_MESSAGE,
            "interaction_id": interaction_id,
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
            persona_text, custom_choice = resolve_persona(organization_id, persona_id)
            if custom_choice:
                answer = _apply_persona(answer, query, persona_text)
            best_similarity = top["similarity"]
            best_kb_result = top
            used_kb_tool = True

    if answer is None:
        answer, best_similarity, used_kb_tool, best_kb_result = _run_tool_loop(query, organization_id, history, persona_id)

    if (used_kb_tool and best_similarity is not None
            and best_similarity >= CITATION_THRESHOLD and best_kb_result):
        source_type = "kb_match"
        answer = f"{answer}\n\nالمصدر: {best_kb_result['source_file']} - الصفحة {best_kb_result['page_number']}"
    else:
        source_type = "fallback_general"
        answer = answer

    latency_ms = int((time.time() - start) * 1000)
    interaction_id = _log_interaction(
        organization_id, user_id, query, answer,
        topic_guard_status="ALLOWED", source_type=source_type,
        similarity_score=best_similarity, latency_ms=latency_ms,
    )

    return {
        "answer": answer,
        "interaction_id": interaction_id,
        "topic_guard_status": "ALLOWED",
        "source_type": source_type,
        "similarity_score": best_similarity,
    }

def submit_feedback(interaction_id: str, rating: str) -> dict:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO feedback (interaction_id, rating) VALUES (%s, %s)",
                    (interaction_id, rating)
                )
        return {'status': 'success', 'interaction_id': interaction_id, 'rating': rating}
    except Exception as e:
        raise ValueError(f"Failed to submit feedback: {str(e)}")
    finally:
        conn.close()