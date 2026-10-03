"""Orchestrates the whole flow: schema -> LLM SQL -> validate -> execute -> answer."""
import logging
import os
from datetime import date, datetime, time as dtime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .agent import CANNOT_ANSWER, generate_sql, is_arabic, normalize_question, summarize_answer
from .schema import get_dialect, get_engine, get_schema
from .validator import SQLValidationError, validate_sql

logger = logging.getLogger("sql_service")

MAX_ROWS = int(os.getenv("SQL_MAX_ROWS", "100"))
TIMEOUT_SECONDS = int(os.getenv("SQL_TIMEOUT_SECONDS", "10"))
MAX_RETRIES = int(os.getenv("SQL_MAX_RETRIES", "2"))


MSG_NOT_ANSWERABLE = {
    "ar": "عذرًا، لا أستطيع الإجابة عن هذا السؤال من قاعدة البيانات.",
    "en": "Sorry, I can't answer this question from the database.",
}
MSG_ERROR = {
    "ar": "عذرًا، حدثت مشكلة أثناء جلب البيانات. برجاء إعادة صياغة السؤال أو المحاولة لاحقًا.",
    "en": "Sorry, something went wrong while fetching the data. Please rephrase or try again later.",
}


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return "<binary>"
    return value


def _execute(sql: str):
    """Run a validated query inside a read-only transaction with a timeout."""
    engine = get_engine()
    dialect = engine.dialect.name
    with engine.connect() as conn:
        if dialect == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {TIMEOUT_SECONDS * 1000}"))
        elif dialect == "mysql":
            try:
                conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
                conn.execute(text(f"SET SESSION max_execution_time = {TIMEOUT_SECONDS * 1000}"))
            except SQLAlchemyError:
                pass  # e.g. MariaDB uses max_statement_time; DB user should be read-only anyway
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [[_json_safe(v) for v in row] for row in result.fetchmany(MAX_ROWS + 1)]
    truncated = len(rows) > MAX_ROWS
    return columns, rows[:MAX_ROWS], truncated


def answer_sql_question(question: str) -> dict:
    """Returns {status: ok|not_answerable|error, answer, sql, columns, rows, row_count, truncated}."""
    question = normalize_question(question)
    lang = "ar" if is_arabic(question) else "en"
    schema = get_schema()
    dialect = get_dialect()

    sql = previous_sql = error = None
    columns, rows, truncated = [], [], False

    for attempt in range(MAX_RETRIES + 1):
        sql = generate_sql(question, schema.text, dialect, MAX_ROWS, previous_sql, error)

        if sql == CANNOT_ANSWER:
            return {"status": "not_answerable", "answer": None, "message": MSG_NOT_ANSWERABLE[lang], "sql": None,
                    "columns": [], "rows": [], "row_count": 0, "truncated": False}
        try:
            safe_sql = validate_sql(sql, dialect, schema.tables, MAX_ROWS)
            columns, rows, truncated = _execute(safe_sql)
            sql = safe_sql
            break
        except (SQLValidationError, SQLAlchemyError) as e:
            previous_sql, error = sql, str(getattr(e, "orig", e))
            logger.warning("SQL attempt %d failed: %s | query: %s", attempt + 1, error, sql)
    else:
        return {"status": "error", "answer": None, "message": MSG_ERROR[lang], "sql": sql, "columns": [], "rows": [],
                "row_count": 0, "truncated": False, "error": error}

    # Audit trail (matches the "Access Controls & Audit Trail" requirement)
    logger.info("SQL_AUDIT question=%r sql=%r rows=%d", question, sql, len(rows))

    answer = summarize_answer(question, sql, columns, rows, truncated)
    return {"status": "ok", "answer": answer, "sql": sql, "columns": columns,
            "rows": rows, "row_count": len(rows), "truncated": truncated}