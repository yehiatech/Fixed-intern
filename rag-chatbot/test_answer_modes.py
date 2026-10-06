# -*- coding: utf-8 -*-
"""Offline test: the complexity LEVEL decides HOW handle_chat answers.
No DB / AWS needed - every external dependency is mocked.  Run: python test_answer_modes.py
"""
import sys, types

# ---- stub the modules chat.py imports (only used by this standalone test)
for name, attrs in {
    "db": {"get_connection": lambda: None},
    "ingestion": {"search_chunks": lambda *a, **k: []},
    "ticket_service": {"create_ticket_record": lambda **k: {"id": "x"}, "TicketError": type("TicketError", (Exception,), {})},
    "personas": {"build_system_prompt": lambda p: p, "resolve_persona": lambda o, p=None: ("persona", False),
                 "HEADER": "", "PERSONA_GUARD": ""},
}.items():
    sys.modules[name] = types.SimpleNamespace(**attrs)
if "boto3" not in sys.modules:
    try:
        import boto3  # noqa: F401
    except ImportError:
        sys.modules["boto3"] = types.SimpleNamespace(client=lambda *a, **k: None)
if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.modules["requests"] = types.SimpleNamespace(RequestException=Exception, get=None)

import chat

CHUNK = lambda t, sim, p=1: {"chunk_text": t, "similarity": sim, "source_file": "doc.pdf", "page_number": p}
calls = {"search_k": None, "synth": 0, "loop": 0, "loop_complex": None}
state = {"results": []}

chat.search_chunks = lambda q, org, top_k=3: (calls.__setitem__("search_k", top_k) or state["results"])
chat._log_interaction = lambda *a, **k: "id-1"
chat._sql_enabled = lambda: False
def fake_synth(chunks, q, persona):
    calls["synth"] += 1
    return "SYNTHESIZED"
def fake_loop(q, org, history=None, persona_id=None, complex_query=False):
    calls["loop"] += 1; calls["loop_complex"] = complex_query
    return "LOOP", 0.5, True, CHUNK("c", 0.5)
chat._synthesize_answer = fake_synth
chat._run_tool_loop = fake_loop

def run(q, results):
    state["results"] = results
    calls.update(search_k=None, synth=0, loop=0, loop_complex=None)
    return chat.handle_chat(q, "org")

SIMPLE = "ساعات العمل ايه؟"
MODERATE = "ايه شروط الاسترجاع وكمان كام يوم عندي للاسترجاع بعد الشراء؟"          # 2 parts -> moderate
COMPLEX = "اشرح لي الفرق بين الباقة الأساسية والمتقدمة وايه المميزات؟ وكمان ازاي ألغي الاشتراك؟"

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    assert cond, name

from complexity import analyze
check("fixture levels", [analyze(SIMPLE).level, analyze(MODERATE).level, analyze(COMPLEX).level] == ["simple", "moderate", "complex"])

r = run(SIMPLE, [CHUNK("نص", 0.8)])
check("simple -> direct chunk, top_k=3, no Bedrock", r["answer_mode"] == "direct" and calls["search_k"] == 3
      and calls["synth"] == 0 and calls["loop"] == 0 and r["answer"].startswith("نص") and "المصدر" in r["answer"])

r = run(MODERATE, [CHUNK("a", 0.8, 1), CHUNK("b", 0.6, 2), CHUNK("c", 0.1, 3)])
check("moderate -> wider search + ONE synthesis call", r["answer_mode"] == "synthesized" and calls["search_k"] == 5
      and calls["synth"] == 1 and calls["loop"] == 0 and r["answer"].startswith("SYNTHESIZED"))
check("moderate cites only chunks above threshold", "الصفحة 1" in r["answer"] and "الصفحة 2" in r["answer"] and "الصفحة 3" not in r["answer"])

r = run(COMPLEX, [CHUNK("a", 0.9)])
check("complex -> tool loop with per-sub-question search, no direct search",
      r["answer_mode"] == "tool_loop" and calls["search_k"] is None and calls["loop"] == 1 and calls["loop_complex"] is True)

r = run(SIMPLE, [CHUNK("a", 0.1)])
check("low similarity falls back to tool loop (not complex mode)", r["answer_mode"] == "tool_loop" and calls["loop_complex"] is False)

chat._synthesize_answer = lambda *a, **k: None
r = run(MODERATE, [CHUNK("a", 0.8)])
check("synthesis failure falls back to tool loop", r["answer_mode"] == "tool_loop" and calls["loop"] == 1)

r = run("عايز اكلم موظف", [CHUNK("a", 0.9)])
check("tools route never uses direct search", r["answer_mode"] == "tool_loop" and calls["search_k"] is None)

r = run("شكراً", [CHUNK("a", 0.9)])
check("small talk: no search, no Bedrock", r["source_type"] == "smalltalk" and calls["search_k"] is None and calls["loop"] == 0)
print("ALL PASSED")