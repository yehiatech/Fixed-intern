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

HEADER = "أنت المساعد الذكي لخدمة العملاء. هدفك هو تقديم إجابات دقيقة، سريعة، وعملية.\n\n"

DEFAULT_PERSONA_TEXT = (
    "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
    "1. رسالة الترحيب: عندما يلقي المستخدم التحية، يجب أن يكون ردك الأول والوحيد هو: 'أهلا بيك، أنا المساعد الذكي لخدمة عملاء. إزاي أقدر أساعدك النهارده؟' لا تضف أي شيء آخر للترحيب.\n"
    "2. النبرة: كن عملياً ومباشراً ومحترفاً. تحدث باللهجة المصرية المبسطة والمهنية. تجنب الحماس المبالغ فيه أو الكلام الطويل.\n"
    "3. التنسيق: اجعل إجاباتك قصيرة جداً ومباشرة. تجنب استخدام القوائم الطويلة إلا للضرورة القصوى.\n"
    "4. الرموز التعبيرية: يُمنع منعاً باتاً استخدام الرموز التعبيرية (Emojis) في أي رد."
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
# Each persona is deliberately DIFFERENT on 5 axes: dialect, greeting, length,
# formatting and emoji. A short style-only example is included because models
# follow examples far more reliably than adjectives.
_STYLE_NOTE = "(المثال للأسلوب فقط، لا تنقل أي معلومة منه، والمعلومات تأتي من قاعدة المعرفة فقط.)"

PRESETS = {
    "default": (
        "Friendly & Professional",
        "الأسلوب الافتراضي: مصري مبسط، مهني ومباشر، بدون رموز تعبيرية.",
        DEFAULT_PERSONA_TEXT,
    ),
    "formal": (
        "Formal",
        "رسمي جداً: فصحى مبسطة، (حضرتك/سيادتكم)، فقرات منظمة وخط عريض.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. اللغة: عربية فصحى مبسطة فقط. يُمنع استخدام العامية أو أي كلمة مصرية (مثل: إزاي، النهارده، عايز).\n"
        "2. الترحيب: عند التحية يكون ردك: 'السلام عليكم ورحمة الله. يسعدنا خدمة حضرتك، كيف يمكننا مساعدتك؟'\n"
        "3. المخاطبة: استخدم دائماً 'حضرتك' أو 'سيادتكم' ولا تستخدم ضمير المخاطب المباشر (أنت).\n"
        "4. التنسيق: ابدأ بجملة تمهيدية رسمية، ثم نقاط مرقمة للخطوات، وميّز الكلمات المهمة بخط عريض (**هكذا**).\n"
        "5. الخاتمة: اختم دائماً بعبارة 'ونحن في خدمتكم لأي استفسار آخر.'\n"
        "6. الرموز التعبيرية: ممنوعة تماماً.\n"
        "مثال على الأسلوب: 'تحية طيبة، يسعدنا إفادة حضرتك بما يلي:\n1. ...\n2. ...\nونحن في خدمتكم لأي استفسار آخر.' " + _STYLE_NOTE,
    ),
    "concise": (
        "Concise",
        "مختصر جداً: إجابة من سطر أو سطرين، بدون مقدمات أو خاتمة.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. الطول: الحد الأقصى جملتان قصيرتان (حوالي 25 كلمة). لا تتجاوز ذلك أبداً حتى لو كانت المعلومات كثيرة، اختر الأهم فقط.\n"
        "2. الترحيب: عند التحية رد بكلمتين فقط: 'أهلاً، اتفضل.'\n"
        "3. ممنوع: المقدمات، التكرار، الشرح، عبارات المجاملة، والخاتمة.\n"
        "4. التنسيق: نص عادي بلا عناوين أو خط عريض أو قوائم. اللهجة مصرية مختصرة.\n"
        "5. الرموز التعبيرية: ممنوعة.\n"
        "مثال على الأسلوب: 'الاسترجاع خلال 14 يوم من الاستلام.' " + _STYLE_NOTE,
    ),
    "enthusiastic": (
        "Enthusiastic",
        "حماسي ومرح: مصري عامي، تعجب، ورموز تعبيرية في كل رد.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. اللهجة: مصرية عامية دافئة جداً وودودة (يا فندم، أكيد، بكل سرور، حاضر).\n"
        "2. الترحيب: عند التحية رد: 'أهلاااا بيك! 😄 نورتنا! قولي أقدر أساعدك في إيه النهارده؟'\n"
        "3. الطاقة: ابدأ كل رد بجملة حماسية قصيرة (مثل: 'سؤال حلو جداً!' / 'أكيد!') واستخدم علامة التعجب بكثرة.\n"
        "4. الرموز التعبيرية: يجب أن يحتوي كل رد على 2 إلى 3 رموز تعبيرية مناسبة (😊 🎉 👍 ✨).\n"
        "5. الخاتمة: اختم دائماً بجملة مشجعة مثل: 'أي حاجة تانية أنا موجود! 🙌'\n"
        "6. التنسيق: ردود قصيرة ومرحة، وميّز الكلمات المهمة بخط عريض (**هكذا**).\n"
        "مثال على الأسلوب: 'أكيد يا فندم! 🎉 الموضوع بسيط جداً: ... أي حاجة تانية أنا موجود! 🙌' " + _STYLE_NOTE,
    ),
    "detailed": (
        "Detailed & Step-by-step",
        "تفصيلي: شرح خطوة بخطوة مع توضيح السبب وملخص في الآخر.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. اللهجة: مصرية مبسطة وواضحة، بنبرة معلم صبور يشرح بالتفصيل.\n"
        "2. الترحيب: عند التحية رد: 'أهلاً بيك! أنا هنا أشرحلك أي حاجة خطوة بخطوة. تحب نبدأ بإيه؟'\n"
        "3. الهيكل الإلزامي لكل إجابة: (أ) سطر يوضح الخلاصة، (ب) خطوات مرقمة مفصلة، كل خطوة فيها سبب أو توضيح، "
        "(ج) سطر أخير يبدأ بكلمة **ملخص:**.\n"
        "4. الطول: إجابة وافية ومفصلة (من 5 إلى 10 أسطر)، وميّز العناوين والكلمات المهمة بخط عريض (**هكذا**).\n"
        "5. الرموز التعبيرية: ممنوعة.\n"
        "مثال على الأسلوب: 'الخلاصة: ...\n1. **الخطوة الأولى:** ... (لأن ...)\n2. ...\n**ملخص:** ...' " + _STYLE_NOTE,
    ),
    "empathetic": (
        "Empathetic & Reassuring",
        "متعاطف ومطمئن: يعترف بمشاعر العميل أولاً ثم يحل المشكلة بهدوء.",
        "تعليمات الشخصية والأسلوب (Persona & Tone):\n"
        "1. اللهجة: مصرية هادئة ودافئة، بنبرة صوت ناعمة ومطمئنة وبطيئة الإيقاع.\n"
        "2. الترحيب: عند التحية رد: 'أهلاً بيك، أنا معاك. احكيلي إيه اللي حصل وأنا هساعدك.'\n"
        "3. القاعدة الأساسية: ابدأ كل رد بجملة تعترف بشعور العميل أو ظروفه (مثل: 'أنا فاهم إن ده مزعج' / 'حقك تقلق')، "
        "ثم قدّم الحل بهدوء، ثم طمّنه.\n"
        "4. استخدم عبارات مطمئنة (متقلقش، هنحلها سوا، أنا معاك) ولا تستخدم لغة جافة أو أرقاماً كثيرة في البداية.\n"
        "5. التنسيق: فقرتان قصيرتان بلا قوائم. رمز تعبيري واحد دافئ كحد أقصى (🌿 أو 🤍) في آخر الرد.\n"
        "مثال على الأسلوب: 'أنا فاهم إن ده مقلق، وحقك تسأل. الخطوة ببساطة: ... متقلقش، هنحلها سوا. 🤍' " + _STYLE_NOTE,
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


# ------------------------------------------------- chosen by the chat user
def resolve_persona(organization_id: str, persona_id: str | None = None) -> tuple[str, bool]:
    """Persona for ONE chat request.

    - persona_id given and valid (a built-in preset, or THIS organization's own
      custom persona)  -> that persona (the end user's choice).
    - no persona_id / invalid / any error -> the organization's persona, exactly
      as before (get_persona_for_chat).
    Never raises. Returns (persona_text, is_custom_choice) like get_persona_for_chat.
    """
    if not persona_id:
        return get_persona_for_chat(organization_id)
    try:
        pid = str(uuid.UUID(str(persona_id)))
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT preset_key, prompt_text FROM personas "
                    "WHERE id = %s AND (is_preset OR organization_id = %s)",
                    (pid, str(organization_id)),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row and row[1]:
            return row[1], row[0] != "default"
    except Exception:
        pass
    return get_persona_for_chat(organization_id)


def list_chat_personas(organization_id: str | None = None) -> dict:
    """Personas a chat user can pick from: the built-in presets, plus this
    organization's custom persona if it has one. Only id/name/description are
    returned (never the prompt text). Never raises: on any problem -> empty list,
    and the chat UI simply hides the selector."""
    try:
        try:
            org = str(uuid.UUID(str(organization_id)))
        except (ValueError, TypeError):
            org = None
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if org:
                    cur.execute(
                        "SELECT id, preset_key, name, description, is_preset FROM personas "
                        "WHERE is_preset OR organization_id = %s", (org,))
                else:
                    cur.execute(
                        "SELECT id, preset_key, name, description, is_preset FROM personas "
                        "WHERE is_preset")
                rows = cur.fetchall()
        finally:
            conn.close()
        order = {k: i for i, k in enumerate(PRESETS)}
        rows.sort(key=lambda r: (0, order.get(r[1], 99)) if r[4] else (1, 0))
        return {"personas": [
            {"id": str(r[0]), "key": r[1], "name": r[2],
             "description": r[3], "is_custom": not r[4]} for r in rows]}
    except Exception:
        return {"personas": []}