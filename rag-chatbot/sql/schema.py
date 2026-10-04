"""Database connection + schema introspection (feeds the LLM prompt and the validator)."""
import os
import threading
import time
from functools import lru_cache
from typing import NamedTuple

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, Engine

_SCHEMA_TTL_SECONDS = 600
_lock = threading.Lock()
_cache = {"info": None, "ts": 0.0}

TENANT_COLUMN = os.getenv("SQL_TENANT_COLUMN", "organization_id")

_DIALECT_MAP = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "tsql",
    "sqlite": "sqlite",
    "oracle": "oracle",
}


class SchemaInfo(NamedTuple):
    text: str               # readable schema description for the LLM
    tables: frozenset       # lower-cased tables the LLM may query
    tenant_tables: frozenset  # subset that has the tenant column (auto-filtered per organization)


def _database_url():
    """SQL_DATABASE_URL if set, otherwise build it from the app's existing DB_* variables."""
    url = os.getenv("SQL_DATABASE_URL")
    if url:
        return url
    host, name = os.getenv("DB_HOST"), os.getenv("DB_NAME")
    if not (host and name):
        raise RuntimeError(
            "Set SQL_DATABASE_URL, or the existing DB_HOST / DB_NAME / DB_USER / DB_PASSWORD variables."
        )
    return URL.create(
        "postgresql+psycopg2",
        # SQL_DB_USER / SQL_DB_PASSWORD let you use a dedicated READ-ONLY user (recommended)
        username=os.getenv("SQL_DB_USER") or os.getenv("DB_USER"),
        password=os.getenv("SQL_DB_PASSWORD") or os.getenv("DB_PASSWORD"),
        host=host,
        port=int(os.getenv("DB_PORT", "5432")),
        database=name,
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # Dedicated engine/pool: never shared with the rest of the application.
    return create_engine(_database_url(), pool_pre_ping=True, pool_recycle=1800)


def get_dialect() -> str:
    name = get_engine().dialect.name
    return _DIALECT_MAP.get(name, name)


def _build_schema() -> SchemaInfo:
    explicit = {
        t.strip().lower()
        for t in os.getenv("SQL_ALLOWED_TABLES", "").split(",")
        if t.strip()
    }
    if not explicit:
        # Fail closed: never expose the whole application database by accident.
        raise RuntimeError("Set SQL_ALLOWED_TABLES to the tables the chatbot may query.")

    insp = inspect(get_engine())
    names = [n for n in sorted(insp.get_table_names() + insp.get_view_names()) if n.lower() in explicit]

    blocks, tenant = [], set()
    for table in names:
        pk_cols = set(insp.get_pk_constraint(table).get("constrained_columns") or [])
        fk_map = {}
        for fk in insp.get_foreign_keys(table):
            for col, ref_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                fk_map[col] = f"{fk['referred_table']}.{ref_col}"

        cols = []
        for c in insp.get_columns(table):
            if c["name"].lower() == TENANT_COLUMN.lower():
                tenant.add(table.lower())
            line = f"{c['name']} {c['type']}"
            if c["name"] in pk_cols:
                line += " PRIMARY KEY"
            if c["name"] in fk_map:
                line += f" REFERENCES {fk_map[c['name']]}"
            if c.get("comment"):
                line += f" /* {c['comment']} */"
            cols.append(line)
        blocks.append(f"TABLE {table} (\n  " + ",\n  ".join(cols) + "\n)")

    return SchemaInfo(
        "\n\n".join(blocks),
        frozenset(n.lower() for n in names),
        frozenset(tenant),
    )


def get_schema(force_refresh: bool = False) -> SchemaInfo:
    with _lock:
        stale = time.time() - _cache["ts"] > _SCHEMA_TTL_SECONDS
        if force_refresh or _cache["info"] is None or stale:
            _cache["info"] = _build_schema()
            _cache["ts"] = time.time()
        return _cache["info"]