"""LLM calls: question -> SQL, and (question + rows) -> natural-language answer.

To use another provider (Gemini, Azure, Ollama...) only change `_chat()`.
"""
import json
import os
import re
from functools import lru_cache

from openai import OpenAI

SQL_MODEL = os.getenv("SQL_LLM_MODEL", "gpt-4o")
CANNOT_ANSWER = "CANNOT_ANSWER"
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def is_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text))


def normalize_question(question: str) -> str:
    """Convert Arabic-Indic digits (١٢٣) to 0-9 and collapse whitespace so SQL filters work."""
    return " ".join(question.translate(_AR_DIGITS).split())


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI()  # reads OPENAI_API_KEY


def _chat(system: str, user: str) -> str:
    resp = _client().chat.completions.create(
        model=SQL_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _clean_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    if m:
        text = m.group(1)
    return text.strip().rstrip(";").strip()


_SQL_SYSTEM = """You are an expert data analyst who converts user questions into SQL.

Rules:
- Output ONLY one {dialect} SELECT statement. No explanations, no markdown.
- Use ONLY the tables and columns in the schema below. Never invent names.
- Never write INSERT/UPDATE/DELETE/DDL. Read-only queries only.
- The question may be in Arabic (Egyptian dialect or MSA) or English. Column and table names are
  in the schema language. Text values in the data may be Arabic or English; for text filters
  prefer LIKE with wildcards over strict equality.
- Common Egyptian/Arabic phrases: كام/كم/عدد = COUNT, إجمالي/مجموع = SUM, متوسط/معدل = AVG,
  أعلى/أكتر/أكبر = ORDER BY DESC, أقل/أصغر = ORDER BY ASC, النهارده = today, امبارح = yesterday,
  الشهر ده/الشهر الحالي = current month, الأسبوع ده = current week, السنة دي = current year,
  مفتوح = open, مغلق/اتقفل = closed, عميل = customer, تذكرة/شكوى = ticket, مكالمة = call.
- Numbers in the question may be Arabic-Indic (١٢٣); treat them as normal digits.
- For "how many" use COUNT, for "total" SUM, for "average" AVG, for "highest/top" ORDER BY ... DESC LIMIT.
- Always add a sensible LIMIT (max {max_rows}).
- If the question cannot be answered from this schema, output exactly: {cannot}

SCHEMA:
{schema}
"""


def generate_sql(question, schema_text, dialect, max_rows, previous_sql=None, error=None) -> str:
    system = _SQL_SYSTEM.format(
        dialect=dialect, max_rows=max_rows, schema=schema_text, cannot=CANNOT_ANSWER
    )
    user = f"Question: {question}"
    if previous_sql and error:
        user += (
            f"\n\nYour previous query failed.\nQuery: {previous_sql}\nError: {error}\n"
            "Fix it and return only the corrected SQL."
        )
    raw = _chat(system, user)
    if CANNOT_ANSWER in raw:
        return CANNOT_ANSWER
    return _clean_sql(raw)


_ANSWER_SYSTEM_EN = """You are a helpful assistant for contact-center agents.
Answer the question using ONLY the query results provided. Do not invent numbers.
- Be concise and clear. For lists, use short bullet points.
- If the results are empty, say no matching data was found.
- If results were truncated, mention that only the first rows are shown."""

_ANSWER_SYSTEM_AR = """أنت مساعد ذكي لمركز اتصال، وبتجاوب بالعربية.
أجب عن السؤال باستخدام نتائج الاستعلام المرفقة فقط، ولا تخترع أي أرقام أو معلومات.
- اكتب الإجابة بالعربية الواضحة والمختصرة (فصحى مبسطة).
- اذكر الأرقام والأسماء كما هي في النتائج بالضبط.
- لو النتائج قائمة، اعرضها في نقاط قصيرة.
- لو النتائج فارغة، قل إنه لا توجد بيانات مطابقة للسؤال.
- لو النتائج مقتطعة (truncated)، اذكر أنه تم عرض أول الصفوف فقط.
- لا تذكر استعلام SQL ولا أسماء الجداول أو الأعمدة في إجابتك."""


def summarize_answer(question, sql, columns, rows, truncated: bool) -> str:
    system = _ANSWER_SYSTEM_AR if is_arabic(question) else _ANSWER_SYSTEM_EN
    payload = json.dumps(
        {"columns": columns, "rows": rows[:50], "truncated": truncated},
        ensure_ascii=False,
        default=str,
    )
    user = f"Question: {question}\n\nSQL used: {sql}\n\nResults (JSON): {payload}"
    return _chat(system, user)