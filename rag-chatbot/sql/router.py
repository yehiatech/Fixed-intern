"""Decides whether a question should go to SQL or to the document RAG pipeline,
and exposes a test endpoint (POST /sql/ask)."""
import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .service import answer_sql_question

# ---------------------------------------------------------------- keywords
SQL_KEYWORDS = [
    # Arabic (written normalized: no hamza on alef, no diacritics)
    "كام", "كم", "عدد", "اجمالي", "اجمالى", "مجموع", "متوسط", "معدل",
    "اعلي", "اعلى", "اقل", "اكبر", "اصغر", "اكتر", "اكثر",
    "اعرض", "عرض", "قائمه", "احسب", "نسبه", "ترتيب", "احصائيات",
    "كام عميل", "كام تذكره", "كام مكالمه", "اخر", "اول",
    # English
    "how many", "count", "total", "average", "sum", "highest", "lowest",
    "top", "most", "least", "maximum", "minimum", "list all",
]

# Words that usually mean "explain a procedure" -> document RAG, not SQL
DOC_HINTS = [
    "خطوات", "ازاي", "كيف", "طريقه", "اجراءات", "سياسه", "شرح", "يعني ايه", "ما هي",
    "how to", "steps", "procedure", "policy", "explain",
]

_DIACRITICS = re.compile(r"[\u064B-\u0652\u0640]")


def _normalize(text: str) -> str:
    text = _DIACRITICS.sub("", text.lower())
    text = re.sub(r"[أإآ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^\w\s]", " ", text)


def _variants(token: str) -> set:
    v = {token}
    for prefix in ("وال", "بال", "لل", "ال", "و"):
        if token.startswith(prefix) and len(token) > len(prefix) + 1:
            v.add(token[len(prefix):])
    return v


_NORM_KEYWORDS = {_normalize(k).strip() for k in SQL_KEYWORDS}
_NORM_HINTS = {_normalize(k).strip() for k in DOC_HINTS}


def _hits(question: str, vocab: set) -> int:
    norm = _normalize(question)
    padded = f" {' '.join(norm.split())} "
    tokens = set()
    for tok in norm.split():
        tokens |= _variants(tok)
    count = 0
    for kw in vocab:
        if " " in kw:
            count += f" {kw} " in padded
        else:
            count += kw in tokens
    return count


def route_question(question: str) -> str:
    """Returns 'sql' or 'rag'."""
    sql_hits = _hits(question, _NORM_KEYWORDS)
    doc_hits = _hits(question, _NORM_HINTS)
    if sql_hits and (sql_hits >= 2 or not doc_hits):
        return "sql"
    return "rag"


# ---------------------------------------------------------------- API
api_router = APIRouter(prefix="/sql", tags=["sql"])


class SQLQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@api_router.post("/ask")
def ask_sql(body: SQLQuestion):
    # plain `def` (not async): the LLM/DB calls are blocking, FastAPI runs them in a threadpool
    return answer_sql_question(body.question)