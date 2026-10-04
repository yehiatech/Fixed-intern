"""Orchestrates the whole flow: schema -> LLM SQL -> validate -> execute -> answer."""
import logging
import os
from datetime import date, datetime, time as dtime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .agent import CANNOT_ANSWER, generate_sql, is_arabic, normalize_question, summarize_answer
from .schema import TENANT_COLUMN, get_dialect, get_engine, get_schema
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
    """Run a validated query in a READ ONLY *transaction* (not session) with a timeout.
    Nothing is left changed on the pooled connection afterwards."""
    engine = get_engine()
    dialect = engine.dialect.name
    ms = TIMEOUT_SECONDS * 1000
    with engine.connect() as conn:
        try:
            if dialect == "postgresql":
                conn.execute(text("SET TRANSACTION READ ONLY"))        # this transaction only
                conn.execute(text(f"SET LOCAL statement_timeout = {ms}"))  # this transaction only
            elif dialect == "mysql":
                conn.exec_driver_sql("START TRANSACTION READ ONLY")    # this transaction only
                try:
                    conn.exec_driver_sql(f"SET SESSION max_execution_time = {ms}")
                except SQLAlchemyError:
                    pass  # MariaDB uses a different variable; DB user should be read-only anyway
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [[_json_safe(v) for v in row] for row in result.fetchmany(MAX_ROWS + 1)]
        finally:
            conn.rollback()  # always ends the read-only transaction
            if dialect == "mysql":
                try:  # undo the only session-level setting we touched
                    conn.exec_driver_sql("SET SESSION max_execution_time = 0")
                    conn.rollback()
                except SQLAlchemyError:
                    pass
    truncated = len(rows) > MAX_ROWS
    return columns, rows[:MAX_ROWS], truncated


def answer_sql_question(question: str, organization_id=None) -> dict:
    """Returns {status: ok|not_answerable|error, answer, message, sql, columns, rows, row_count, truncated}."""
    question = normalize_question(question)
    lang = "ar" if is_arabic(question) else "en"
    schema = get_schema()
    dialect = get_dialect()

    sql = previous_sql = error = None
    columns, rows, truncated = [], [], False

    for attempt in range(MAX_RETRIES + 1):
        sql = generate_sql(question, schema.text, dialect, MAX_ROWS, previous_sql, error)

        if sql == CANNOT_ANSWER:
            return {"status": "not_answerable", "answer": None, "message": MSG_NOT_ANSWERABLE[lang],
                    "sql": None, "columns": [], "rows": [], "row_count": 0, "truncated": False}
        try:
            safe_sql = validate_sql(
                sql, dialect, schema.tables, MAX_ROWS,
                tenant_tables=schema.tenant_tables,
                organization_id=organization_id,
                tenant_column=TENANT_COLUMN,
            )
            columns, rows, truncated = _execute(safe_sql)
            sql = safe_sql
            break
        except (SQLValidationError, SQLAlchemyError) as e:
            previous_sql, error = sql, str(getattr(e, "orig", e))
            logger.warning("SQL attempt %d failed: %s | query: %s", attempt + 1, error, sql)
    else:
        return {"status": "error", "answer": None, "message": MSG_ERROR[lang], "sql": sql,
                "columns": [], "rows": [], "row_count": 0, "truncated": False, "error": error}

    logger.info("SQL_AUDIT org=%s question=%r sql=%r rows=%d", organization_id, question, sql, len(rows))

    answer = summarize_answer(question, sql, columns, rows, truncated)
    return {"status": "ok", "answer": answer, "sql": sql, "columns": columns,
            "rows": rows, "row_count": len(rows), "truncated": truncated}