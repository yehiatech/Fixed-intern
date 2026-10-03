"""Safety layer: only a single, read-only SELECT on allowed tables may reach the database."""
import re

import sqlglot
from sqlglot import exp


class SQLValidationError(ValueError):
    pass


_FORBIDDEN_NAMES = [
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Merge",
    "TruncateTable", "Into", "Lock", "Set", "Use", "Grant", "Copy", "Transaction",
    "Commit", "Rollback", "Pragma", "Attach",
]
_FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))

_FORBIDDEN_FUNCS = {
    "pg_sleep", "sleep", "benchmark", "load_file", "pg_read_file", "pg_ls_dir",
    "lo_import", "lo_export", "dblink", "xp_cmdshell", "set_config", "sys_exec",
}

_DANGEROUS_PATTERN = re.compile(
    r"\b(into\s+outfile|into\s+dumpfile|information_schema|pg_catalog|sqlite_master)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str, dialect: str, allowed_tables: frozenset, max_rows: int) -> str:
    """Return a safe, re-generated SQL string (with enforced LIMIT) or raise SQLValidationError."""
    if not sql or not sql.strip():
        raise SQLValidationError("Empty query.")

    if _DANGEROUS_PATTERN.search(sql):
        raise SQLValidationError("Query touches restricted system objects.")

    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SQLValidationError(f"SQL could not be parsed: {e}")

    if len(statements) != 1:
        raise SQLValidationError("Exactly one SQL statement is allowed.")

    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise SQLValidationError("Only SELECT queries are allowed.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}

    for node in tree.walk():
        node = node[0] if isinstance(node, tuple) else node  # older sqlglot yields tuples

        if isinstance(node, _FORBIDDEN_NODES):
            raise SQLValidationError(f"Forbidden operation: {type(node).__name__}.")

        if isinstance(node, exp.Anonymous) and node.name.lower() in _FORBIDDEN_FUNCS:
            raise SQLValidationError(f"Forbidden function: {node.name}.")

        if isinstance(node, exp.Table):
            if node.args.get("db") or node.args.get("catalog"):
                raise SQLValidationError("Schema/database-qualified tables are not allowed.")
            name = node.name.lower()
            if name and name not in cte_names and name not in allowed_tables:
                raise SQLValidationError(f"Table '{node.name}' is not allowed.")

    # Enforce a row cap
    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name)
        except (ValueError, AttributeError):
            current = None
    if current is None or current > max_rows:
        tree = tree.limit(max_rows)

    # We execute the *regenerated* SQL (comments stripped, normalized), not the raw LLM text.
    return tree.sql(dialect=dialect)