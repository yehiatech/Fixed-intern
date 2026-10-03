"""Database connection + schema introspection (feeds the LLM prompt and the validator)."""
import os
import threading
import time
from functools import lru_cache
from typing import NamedTuple

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

_SCHEMA_TTL_SECONDS = 600
_lock = threading.Lock()
_cache = {"info": None, "ts": 0.0}

_DIALECT_MAP = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "tsql",
    "sqlite": "sqlite",
    "oracle": "oracle",
}


class SchemaInfo(NamedTuple):
    text: str              # human/LLM readable schema description
    tables: frozenset      # lower-cased table names the LLM is allowed to query


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = os.getenv("SQL_DATABASE_URL")
    if not url:
        raise RuntimeError("SQL_DATABASE_URL is not set in the environment / .env")
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


def get_dialect() -> str:
    """Dialect name in sqlglot's vocabulary."""
    name = get_engine().dialect.name
    return _DIALECT_MAP.get(name, name)


def _build_schema() -> SchemaInfo:
    engine = get_engine()
    insp = inspect(engine)

    explicit = {
        t.strip().lower()
        for t in os.getenv("SQL_ALLOWED_TABLES", "").split(",")
        if t.strip()
    }
    names = sorted(insp.get_table_names() + insp.get_view_names())
    if explicit:
        names = [n for n in names if n.lower() in explicit]

    blocks = []
    for table in names:
        pk_cols = set(insp.get_pk_constraint(table).get("constrained_columns") or [])
        fk_map = {}
        for fk in insp.get_foreign_keys(table):
            for col, ref_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                fk_map[col] = f"{fk['referred_table']}.{ref_col}"

        cols = []
        for c in insp.get_columns(table):
            line = f"{c['name']} {c['type']}"
            if c["name"] in pk_cols:
                line += " PRIMARY KEY"
            if c["name"] in fk_map:
                line += f" REFERENCES {fk_map[c['name']]}"
            if c.get("comment"):
                line += f" /* {c['comment']} */"
            cols.append(line)

        blocks.append(f"TABLE {table} (\n  " + ",\n  ".join(cols) + "\n)")

    return SchemaInfo("\n\n".join(blocks), frozenset(n.lower() for n in names))


def get_schema(force_refresh: bool = False) -> SchemaInfo:
    """Cached schema (refreshed every 10 min or on demand)."""
    with _lock:
        stale = time.time() - _cache["ts"] > _SCHEMA_TTL_SECONDS
        if force_refresh or _cache["info"] is None or stale:
            _cache["info"] = _build_schema()
            _cache["ts"] = time.time()
        return _cache["info"]