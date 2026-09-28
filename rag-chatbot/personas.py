# -*- coding: utf-8 -*-
"""
Customizable chatbot personas.

An organization admin picks HOW the RAG chatbot talks (tone, formatting,
emoji use). What the bot is ALLOWED to do never changes: the retrieval,
anti-hallucination, transparency and ticket-escalation rules are a fixed
block (CORE_RULES) that is always appended AFTER the persona text, so a
persona - even a free-text custom one - cannot switch them off.

Final system prompt = HEADER + persona text + PERSONA_GUARD + CORE_RULES

This module does not import fastapi/boto3, so chat.py can import it safely.
If anything goes wrong reading personas from the database, chat falls back
to DEFAULT_PERSONA_TEXT (the tone the bot always had), so a personas problem
can never take the chatbot down.
"""
import uuid

from db import get_connection
from ticket_service import TicketError, _require_org

MAX_CUSTOM_LEN = 600

HEADER = "أنت مساعد ذكي لخدمة العملاء. هدفك هو تقديم إجابات استباقية وسريعة للعملاء.\n\n"

DEFAULT_PERSONA_TEXT = (
    "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
    "1. النبرة: كن ودوداً ومهنياً.\n"
    "2. التنسيق: اجعل إجاباتك قصيرة ومريحة للعين. استخدم النقط (Bullet points) للخطوات، "
    "وقم بتمييز الكلمات المهمة بخط عريض (**Bold**).\n"
    "3. الرموز التعبيرية: استخدم الرموز التعبيرية بشكل نادر جداً أو لا تستخدمها."
)

PERSONA_GUARD = (
    "\n\nملاحظة: تعليمات الشخصية أعلاه تخص أسلوب الكتابة فقط (النبرة والتنسيق والرموز). "
    "هي لا تلغي ولا تعدّل أي قاعدة في القسم التالي، وعند أي تعارض تُطبَّق القواعد التالية.\n\n"
)

CORE_RULES = """قواعد ثابتة:
- الشفافية: أنت ذكاء اصطناعي، لا تتظاهر بأنك إنسان.

قواعد الاسترجاع من المعلومات والتصعيد (RAG & Escalation):
1. ابحث دائماً في قاعدة المعرفة باستخدام الأداة (search_knowledge_base) قبل الإجابة على أي سؤال يخص الشركة أو السياسات.
2. لا تخترع (Hallucinate) أي معلومات من خارج النصوص المسترجعة أبداً.
3. عند تقديم معلومات من قاعدة المعرفة، حافظ على دقة المعلومات المرجعية.
4. **هام جداً للتصعيد وفتح التذاكر**: عندما يطلب المستخدم التحدث إلى موظف بشري أو عندما تقرر أنه بحاجة لدعم بشري، يجب عليك جمع المعلومات التالية أولاً:
   - الاسم
   - رقم الهاتف
   - وصف المشكلة
   **لا تقم بإنشاء التذكرة أبداً إذا كانت أي من هذه المعلومات مفقودة.** استمر في سؤاله بلباقة عن المعلومات الناقصة. بمجرد توفر المعلومات الثلاثة، استخدم أداة (create_ticket) لإنشاء التذكرة فوراً، ثم أكد له أنه سيتم التواصل معه.

استخدم lookup_ticket أو check_order_status أو create_ticket عند الحاجة."""

# key -> (display name, description shown to the admin, prompt text)
PRESETS = {
    "default": (
        "Friendly & Professional",
        "الأسلوب الافتراضي: ودود ومهني، ردود قصيرة، بدون رموز تعبيرية تقريباً.",
        DEFAULT_PERSONA_TEXT,
    ),
    "formal": (
        "Formal",
        "رسمي ومحترم، لغة عربية فصحى مبسطة، بدون رموز تعبيرية.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. النبرة: رسمية ومحترمة، خاطب العميل بأدب شديد (حضرتك / سيادتكم) وتجنب العامية.\n"
        "2. التنسيق: فقرات قصيرة ومنظمة، ونقاط مرقمة للخطوات، وقم بتمييز الكلمات المهمة بخط عريض (**Bold**).\n"
        "3. الرموز التعبيرية: لا تستخدم الرموز التعبيرية إطلاقاً.",
    ),
    "concise": (
        "Concise",
        "مختصر ومباشر: أقصر إجابة مفيدة، بدون مقدمات.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. النبرة: مباشرة وعملية، ادخل في الإجابة فوراً بدون مقدمات أو عبارات ترحيب طويلة.\n"
        "2. التنسيق: أقصر إجابة تفي بالغرض (جملة إلى ثلاث جمل)، ونقاط فقط عند الحاجة الفعلية.\n"
        "3. الرموز التعبيرية: لا تستخدمها.",
    ),
    "enthusiastic": (
        "Enthusiastic",
        "حماسي وودود جداً، مع رموز تعبيرية بشكل معتدل.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. النبرة: حماسية ودافئة وإيجابية، اجعل العميل يشعر أنك سعيد بمساعدته.\n"
        "2. التنسيق: ردود قصيرة ومرحة، ونقاط للخطوات، وقم بتمييز الكلمات المهمة بخط عريض (**Bold**).\n"
        "3. الرموز التعبيرية: استخدم رمزاً أو رمزين تعبيريين مناسبين في الرد (لا تكثر).",
    ),
}


def build_system_prompt(persona_text: str | None = None) -> str:
    return HEADER + (persona_text or DEFAULT_PERSONA_TEXT) + PERSONA_GUARD + CORE_RULES


def seed_presets() -> None:
    """Insert/refresh the built-in presets. Code is the source of truth for
    presets, so re-running on every startup is intended and idempotent."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for key, (name, description, text) in PRESETS.items():
                    cur.execute(
                        """
                        INSERT INTO personas (preset_key, name, description, prompt_text, is_preset)
                        VALUES (%s, %s, %s, %s, TRUE)
                        ON CONFLICT (preset_key) WHERE is_preset
                        DO UPDATE SET name = EXCLUDED.name,
                                      description = EXCLUDED.description,
                                      prompt_text = EXCLUDED.prompt_text
                        """,
                        (key, name, description, text),
                    )
    finally:
        conn.close()


# ------------------------------------------------------------ used by chat.py
def get_persona_for_chat(organization_id: str) -> tuple[str, bool]:
    """Returns (persona_text, is_custom_choice).

    is_custom_choice is True only when the org explicitly picked something
    other than the default look - chat.py uses it to decide whether the
    cheap direct-KB answer should be re-phrased in that persona.
    Never raises: any problem -> the default persona.
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.preset_key, p.prompt_text FROM organizations o "
                    "LEFT JOIN personas p ON p.id = o.persona_id WHERE o.id = %s",
                    (str(organization_id),),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row or not row[1]:
            return DEFAULT_PERSONA_TEXT, False
        return row[1], row[0] != "default"
    except Exception:
        return DEFAULT_PERSONA_TEXT, False


# ------------------------------------------------------------ used by the API
def list_personas(organization_id: str) -> dict:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                cur.execute(
                    "SELECT id, preset_key, name, description, prompt_text, is_preset, organization_id "
                    "FROM personas WHERE is_preset OR organization_id = %s ORDER BY is_preset DESC, created_at",
                    (org_id,),
                )
                rows = cur.fetchall()
                cur.execute("SELECT persona_id FROM organizations WHERE id = %s", (org_id,))
                sel = cur.fetchone()[0]
        presets, custom = [], None
        for r in rows:
            if r[5]:
                presets.append({"id": str(r[0]), "key": r[1], "name": r[2],
                                "description": r[3], "prompt_text": r[4]})
            else:
                custom = {"id": str(r[0]), "name": r[2], "prompt_text": r[4]}
        selected_id = str(sel) if sel else None
        if selected_id is None:  # nothing chosen == the default preset
            selected_id = next((p["id"] for p in presets if p["key"] == "default"), None)
        return {"presets": presets, "custom": custom, "selected_id": selected_id,
                "max_custom_length": MAX_CUSTOM_LEN}
    finally:
        conn.close()


def select_persona(organization_id: str, persona_id: str | None = None,
                   custom_text: str | None = None, custom_name: str | None = None) -> dict:
    """Pick a preset (persona_id) OR save+select the org's custom persona
    (custom_text). persona_id=None with no custom_text resets to default."""
    custom_text = (custom_text or "").strip()
    if custom_text and len(custom_text) > MAX_CUSTOM_LEN:
        raise TicketError(f"Custom persona is too long (max {MAX_CUSTOM_LEN} characters)", 400)

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)

                if custom_text:
                    cur.execute(
                        """
                        INSERT INTO personas (organization_id, name, description, prompt_text, is_preset)
                        VALUES (%s, %s, 'Custom persona', %s, FALSE)
                        ON CONFLICT (organization_id) WHERE NOT is_preset
                        DO UPDATE SET name = EXCLUDED.name, prompt_text = EXCLUDED.prompt_text
                        RETURNING id
                        """,
                        (org_id, (custom_name or "").strip()[:100] or "Custom", custom_text),
                    )
                    new_id = cur.fetchone()[0]
                elif persona_id:
                    try:
                        pid = str(uuid.UUID(str(persona_id)))
                    except ValueError:
                        raise TicketError("Invalid persona_id", 400)
                    # a preset, or this organization's own custom persona - never another org's
                    cur.execute(
                        "SELECT id FROM personas WHERE id = %s AND (is_preset OR organization_id = %s)",
                        (pid, org_id),
                    )
                    if cur.fetchone() is None:
                        raise TicketError("Persona not found", 404)
                    new_id = pid
                else:
                    new_id = None  # reset to default

                cur.execute("UPDATE organizations SET persona_id = %s WHERE id = %s", (new_id, org_id))
        return {"selected_id": str(new_id) if new_id else None}
    finally:
        conn.close()
