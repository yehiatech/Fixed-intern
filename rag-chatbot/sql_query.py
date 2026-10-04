"""Adapter for chat.py:  from sql_query import run_structured_query

Keeps the 3-argument signature chat.py already uses and delegates to the SQL module.
`get_connection` is accepted for compatibility but not used: the SQL module has its own
read-only SQLAlchemy engine (see sql/schema.py), so it never touches the app's connections.
"""
import logging

from sql.service import answer_sql_question

logger = logging.getLogger("sql_query")


def run_structured_query(question: str, organization_id=None, get_connection=None) -> dict:
    """Never raises: returns {status: ok|not_answerable|error, answer|message, sql, rows, ...}."""
    try:
        return answer_sql_question(question, organization_id=organization_id)
    except Exception:  # config problems, DB down, LLM down...
        logger.exception("run_structured_query failed")
        return {
            "status": "error",
            "answer": None,
            "message": "عذرًا، تعذر الوصول إلى البيانات حاليًا. برجاء المحاولة لاحقًا.",
            "sql": None, "columns": [], "rows": [], "row_count": 0, "truncated": False,
        }