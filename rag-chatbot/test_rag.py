"""Smoke tests for the Text-to-SQL module.

Run from the rag-chatbot/ folder with the venv active:

  python test_sql_smoke.py                 # 1) offline: validator + router (no DB, no LLM)
  python test_sql_smoke.py --db            # 2) + connect to YOUR database and print the schema
  python test_sql_smoke.py --demo --e2e    # 3) full flow on a temporary SQLite demo DB (needs OPENAI_API_KEY)
  python test_sql_smoke.py --e2e           # 4) full flow on YOUR database (needs OPENAI_API_KEY)
  python test_sql_smoke.py --e2e --q "كام عميل عندنا؟"   # ask one custom question
"""
import argparse
import os
import sqlite3
import sys
import tempfile

try:  # make Arabic print correctly on Windows terminals
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

failures = 0


def check(name: str, ok: bool, detail: str = ""):
    global failures
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures += 1


# ------------------------------------------------------------------ demo DB
def make_demo_db() -> str:
    path = os.path.join(tempfile.gettempdir(), "rag_sql_demo.db")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT, created_at TEXT);
        CREATE TABLE tickets (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
                              status TEXT, subject TEXT, created_at TEXT);
        INSERT INTO customers VALUES
          (1,'أحمد علي','القاهرة','2026-08-01'), (2,'منى حسن','الإسكندرية','2026-08-10'),
          (3,'محمود سمير','القاهرة','2026-09-02'), (4,'سارة يوسف','الجيزة','2026-09-15');
        INSERT INTO tickets VALUES
          (1,1,'open','مشكلة في الفاتورة','2026-09-20'), (2,1,'closed','تحديث بيانات','2026-09-01'),
          (3,2,'open','تأخر التوصيل','2026-09-25'), (4,3,'open','استفسار عن الباقة','2026-09-27'),
          (5,4,'closed','تغيير رقم الهاتف','2026-09-10');
        """
    )
    con.commit()
    con.close()
    os.environ["SQL_DATABASE_URL"] = f"sqlite:///{path}"
    os.environ["SQL_ALLOWED_TABLES"] = "customers,tickets"
    return path


# ------------------------------------------------------------------ tests
def test_validator():
    print("\n== Validator (offline) ==")
    from sql.validator import SQLValidationError, validate_sql

    allowed = frozenset({"customers", "tickets"})

    good = [
        "SELECT COUNT(*) FROM customers",
        "SELECT c.name FROM customers c JOIN tickets t ON t.customer_id = c.id WHERE t.status = 'open'",
        "WITH x AS (SELECT * FROM tickets) SELECT COUNT(*) FROM x",
    ]
    for q in good:
        try:
            validate_sql(q, "postgres", allowed, 100)
            check(f"allows: {q[:55]}", True)
        except SQLValidationError as e:
            check(f"allows: {q[:55]}", False, str(e))

    bad = [
        "DROP TABLE customers",
        "DELETE FROM tickets",
        "UPDATE customers SET name = 'x'",
        "SELECT * FROM users",                       # table not in allow-list
        "SELECT 1; DROP TABLE customers",            # stacked statements
        "SELECT * FROM customers INTO OUTFILE '/tmp/x'",
        "SELECT pg_sleep(10)",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM public.customers",            # schema-qualified
    ]
    for q in bad:
        try:
            validate_sql(q, "postgres", allowed, 100)
            check(f"blocks: {q[:55]}", False, "was NOT blocked")
        except SQLValidationError:
            check(f"blocks: {q[:55]}", True)

    out = validate_sql("SELECT * FROM customers LIMIT 100000", "postgres", allowed, 100)
    check("caps huge LIMIT to 100", "100000" not in out and "100" in out, out)
    out = validate_sql("SELECT * FROM customers", "postgres", allowed, 100)
    check("adds LIMIT when missing", "LIMIT 100" in out.upper(), out)


def test_router():
    print("\n== Router (offline) ==")
    from sql.router import route_question

    cases = [
        ("كام عميل عندنا في القاهرة؟", "sql"),
        ("إجمالي التذاكر المفتوحة الشهر ده", "sql"),
        ("اعرض أعلى 5 عملاء", "sql"),
        ("how many open tickets do we have", "sql"),
        ("ما هي خطوات تحديث بيانات العميل في النظام الداخلي؟", "rag"),
        ("ازاي أغير رقم تليفون العميل؟", "rag"),
    ]
    for q, expected in cases:
        got = route_question(q)
        check(f"{q}  => {expected}", got == expected, f"got {got}")


def test_db():
    print("\n== Database + schema ==")
    from sql.schema import get_dialect, get_schema

    try:
        info = get_schema(force_refresh=True)
        check("connected and read schema", True)
        print(f"  dialect: {get_dialect()}")
        print(f"  allowed tables ({len(info.tables)}): {', '.join(sorted(info.tables))}")
        check("at least one table visible", len(info.tables) > 0,
              "check SQL_ALLOWED_TABLES spelling / DB user privileges")
        print("\n  --- schema preview (what the LLM sees) ---")
        for line in info.text.splitlines()[:25]:
            print("  " + line)
    except Exception as e:
        check("connected and read schema", False, repr(e))


DEFAULT_QUESTIONS = [
    "كام عميل عندنا؟",
    "كام تذكرة مفتوحة؟",
    "اعرض العملاء اللي في القاهرة",
    "إجمالي عدد التذاكر لكل عميل",
    "ما هي خطوات تحديث بيانات العميل؟",      # should route to RAG, not SQL
    "كام عميل عنده موبايل ٥ نجوم؟",           # unanswerable -> graceful message
]


def test_e2e(questions):
    print("\n== End-to-end (LLM + DB) ==")
    if not os.getenv("OPENAI_API_KEY"):
        check("OPENAI_API_KEY is set", False, "add it to .env")
        return
    from sql.router import route_question
    from sql.service import answer_sql_question

    for q in questions:
        print(f"\n  Q: {q}")
        route = route_question(q)
        print(f"  route: {route}")
        if route != "sql":
            print("  -> would go to your normal RAG pipeline (skipped here)")
            continue
        try:
            r = answer_sql_question(q)
        except Exception as e:
            check("pipeline ran", False, repr(e))
            continue
        print(f"  status: {r['status']}")
        if r.get("sql"):
            print(f"  sql: {r['sql']}")
        print(f"  rows: {r['row_count']}")
        print(f"  answer: {r.get('answer') or r.get('message')}")
        check("no crash", True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="connect to the database and print the schema")
    ap.add_argument("--demo", action="store_true", help="use a temporary SQLite demo database")
    ap.add_argument("--e2e", action="store_true", help="run full LLM + DB questions")
    ap.add_argument("--q", help="a single custom question for --e2e")
    args = ap.parse_args()

    if args.demo:
        print(f"Demo SQLite DB created at {make_demo_db()}")

    test_validator()
    test_router()
    if args.db or args.demo or args.e2e:
        test_db()
    if args.e2e:
        test_e2e([args.q] if args.q else DEFAULT_QUESTIONS)

    print(f"\n{'ALL CHECKS PASSED' if failures == 0 else str(failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)