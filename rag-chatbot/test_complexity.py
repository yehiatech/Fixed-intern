# -*- coding: utf-8 -*-
"""Offline tests (no DB, no AWS):  python test_complexity.py"""
import sys

from complexity import analyze, detect_smalltalk

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if not ok else ""))
    failures += 0 if ok else 1


ASSISTANT_ASKS_NAME = [{"role": "assistant", "content": [{"text": "ما هو اسمك؟"}]}]

print("Small talk -> answered with no retrieval")
for msg in ["hi", "Hello!", "هاي", "هاااي", "السلام عليكم", "السلام عليكم ورحمة الله وبركاته",
            "صباح الخير", "ازيك عامل ايه", "hi how are you", "bye", "مع السلامة", "يلا سلام",
            "شكرا", "شكراً جزيلاً", "thanks a lot", "thank you bye", "تمام", "مرحبا 👋", "سلام"]:
    a = analyze(msg)
    check(f"smalltalk: {msg!r}", a.route == "smalltalk" and a.reply, f"{a.route}")

print("Real questions that merely START with a greeting must NOT be small talk")
for msg in ["hi, what is the vacation policy?", "السلام عليكم عايز اعرف سياسة الاجازات",
            "شكرا بس لسه مش فاهم الخصم", "ok but how do I reset my password", "سلام ما هي ساعات العمل",
            "", "؟؟؟", "👍"]:
    check(f"not smalltalk: {msg!r}", detect_smalltalk(msg) is None)

print("Bot asked a question -> a bare 'سلام' / 'ok' is an answer, not small talk")
check("answer 'سلام' (a name) goes to the LLM", analyze("سلام", ASSISTANT_ASKS_NAME).route != "smalltalk")
check("'شكرا' still shortcut", analyze("شكرا", ASSISTANT_ASKS_NAME).route == "smalltalk")

print("Routing / complexity")
cases = [
    ("ما هي سياسة الإجازات؟", "rag", "simple"),
    ("عايز اتكلم مع موظف", "tools", None),
    ("I want to talk to a human agent", "tools", None),
    ("افتح لي تذكرة", "tools", None),
    ("ما حالة تذكرة رقم 1234", "tools", None),
    ("كام تذكرة مفتوحة النهارده؟", "sql", None),
    ("how many tickets are open today", "sql", None),
    ("وين طلب رقم 99812", "tools", None),
    ("ما سياسة الاجازات المرضية؟ وكمان ايه الفرق بينها وبين الاجازات السنوية؟ واشرح لي خطوات التقديم", "rag", "complex"),
    ("كام يوم قبل السفر لازم أحجز تذكرة طيران؟", "rag", None),   # not a support-ticket count
    ("كام تذكرة معلقة؟", "sql", None),
    ("سياسة اجازات الموظفين", "rag", "simple"),          # "موظف" alone must not trigger a ticket
]
for msg, route, level in cases:
    a = analyze(msg)
    check(f"{msg[:40]!r} -> {route}" + (f"/{level}" if level else ""),
          a.route == route and (level is None or a.level == level),
          f"got {a.route}/{a.level} score={a.score} {a.reasons}")

print("Ticket-info collection turn forces the tool path")
hist = [{"role": "assistant", "content": [{"text": "ما هو رقم الهاتف الخاص بك؟"}]}]
check("phone number reply", analyze("01012345678", hist).route == "tools")

print("SQL disabled -> structured question falls back to normal tools/rag, never 'sql'")
check("sql_enabled=False", analyze("كام تذكرة مفتوحة؟", sql_enabled=False).route != "sql")

print("ETA ordering: smalltalk < rag simple < tools < sql")
etas = [analyze(m).eta_seconds[1] for m in
        ["hi", "ما هي سياسة الإجازات؟", "عايز اتكلم مع موظف", "كام تذكرة مفتوحة؟"]]
check("increasing", etas == sorted(etas) and len(set(etas)) == 4, str(etas))

print(f"\n{'ALL PASSED' if not failures else str(failures) + ' FAILED'}")
sys.exit(1 if failures else 0)
