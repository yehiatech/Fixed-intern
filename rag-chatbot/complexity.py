# -*- coding: utf-8 -*-
"""
Message triage, run BEFORE any retrieval / Bedrock call. Pure Python, ~1 ms.

analyze(query, history) answers three questions about an incoming message:

  1. Is it just small talk (hi / bye / thanks ...)?  -> route "smalltalk":
     a canned reply is returned, with NO retrieval and NO LLM call.
  2. How complex is it?  -> score 0-100 and level simple / moderate / complex.
  3. Which path will it take, and roughly how long will that take?
        route "rag"   : direct knowledge-base search (fast path)
        route "tools" : needs the Bedrock tool loop (ticket, lookup, order...)
        route "sql"   : needs Text-to-SQL (slowest)

The ETA numbers in ETA_SECONDS are estimates derived from the code path
(embedding + pgvector query vs. 1..5 Bedrock round-trips). Calibrate them
from the latency_ms column you already log (see README note / test file).
"""
import random
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Text normalisation (Arabic + English)
# --------------------------------------------------------------------------
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_REPEAT = re.compile(r"(.)\1{2,}")          # "هاااي" -> "هاي", "hiii" -> "hi"
_ARABIC_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})
_HAS_ARABIC = re.compile(r"[\u0600-\u06FF]")


def normalize(text: str) -> str:
    t = (text or "").lower().strip()
    t = _DIACRITICS.sub("", t)
    t = t.translate(_ARABIC_MAP)
    t = _REPEAT.sub(r"\1", t)
    t = _NON_WORD.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


# --------------------------------------------------------------------------
# Small talk
# --------------------------------------------------------------------------
# Written in natural spelling; normalised at import so matching is spelling-tolerant.
_SMALLTALK_SOURCE = {
    "greeting": [
        "hi", "hii", "hello", "hey", "heya", "good morning", "good afternoon", "good evening",
        "هاي", "هلا", "هلو", "اهلا", "اهلا وسهلا", "اهلا بيك", "اهلا بك", "اهلين", "مرحبا", "مرحبتين",
        "نورت", "السلام عليكم", "سلام عليكم", "وعليكم السلام", "ورحمه الله", "وبركاته",
        "صباح الخير", "صباح النور", "مساء الخير", "مساء النور", "صباحو", "مساء الفل", "صباح الفل",
    ],
    "how_are_you": [
        "how are you", "how r u", "how are u", "hows it going", "whats up", "sup",
        "ازيك", "ازيكم", "عامل ايه", "عاملين ايه", "اخبارك", "اخباركم", "ايه الاخبار", "ايه اخبارك",
        "كيف حالك", "كيف الحال", "شلونك", "ازاي حالك",
    ],
    "farewell": [
        "bye", "goodbye", "good bye", "see you", "see ya", "cya", "take care", "good night",
        "باي", "مع السلامه", "الي اللقاء", "في امان الله", "في رعايه الله", "تصبح علي خير",
        "تصبحوا علي خير", "نشوفك بعدين", "يلا باي", "يلا سلام", "سلامو عليكم",
    ],
    "thanks": [
        "thanks", "thank you", "thank u", "thx", "ty", "many thanks", "thanks a lot",
        "شكرا", "شكرا لك", "شكرا ليك", "شكرا جزيلا", "الف شكر", "متشكر", "متشكره", "تسلم", "تسلمي",
        "ميرسي", "مرسي", "كتر خيرك", "جزاك الله خيرا", "يعطيك العافيه",
    ],
    "ack": [
        "ok", "okay", "k", "alright", "got it", "اوكي", "اوك", "تمام", "حاضر", "ماشي", "طيب", "كده تمام",
    ],
    "neutral": ["سلام"],          # "سلام" alone can be hello OR bye
    "filler": ["يا", "بوت", "جدا", "كتير", "اوي", "ليك", "لك", "كده", "جميعا", "بيك", "بك", "very", "much"],
}

_PHRASES: dict[str, str] = {}
for _cat, _items in _SMALLTALK_SOURCE.items():
    for _p in _items:
        _PHRASES[normalize(_p)] = _cat
_MAX_PHRASE_LEN = max(len(p.split()) for p in _PHRASES)
_MAX_SMALLTALK_TOKENS = 8
_QUESTION_MARK = re.compile(r"[?؟]")

_REPLIES = {
    "ar": {
        "greeting": ["أهلاً بك! أنا المساعد الذكي، كيف يمكنني مساعدتك اليوم؟",
                     "مرحباً! تفضّل، كيف أقدر أساعدك؟"],
        "salam": ["وعليكم السلام ورحمة الله وبركاته! كيف يمكنني مساعدتك اليوم؟"],
        "how_are_you": ["أنا بخير، شكراً لسؤالك! كيف يمكنني مساعدتك اليوم؟"],
        "greeting_how": ["أهلاً بك! أنا بخير، شكراً لسؤالك. كيف يمكنني مساعدتك اليوم؟"],
        "thanks": ["العفو! إذا احتجت أي مساعدة أخرى فأنا هنا.",
                   "على الرحب والسعة! هل هناك شيء آخر يمكنني مساعدتك به؟"],
        "farewell": ["مع السلامة! سعدت بمساعدتك.",
                     "إلى اللقاء! لا تتردد في العودة إذا احتجت أي شيء."],
        "ack": ["تمام! أخبرني إذا احتجت أي شيء آخر."],
        "neutral": ["سلام! إذا احتجت أي مساعدة فأنا هنا."],
    },
    "en": {
        "greeting": ["Hello! I'm your virtual assistant. How can I help you today?",
                     "Hi there! What can I help you with?"],
        "salam": ["Wa alaykum assalam! How can I help you today?"],
        "how_are_you": ["I'm doing well, thanks for asking! How can I help you today?"],
        "greeting_how": ["Hello! I'm doing well, thanks for asking. How can I help you today?"],
        "thanks": ["You're welcome! Let me know if you need anything else.",
                   "Happy to help! Is there anything else I can do for you?"],
        "farewell": ["Goodbye! It was a pleasure helping you.",
                     "Take care! Come back any time you need help."],
        "ack": ["Great! Let me know if you need anything else."],
        "neutral": ["Hi! Let me know if you need any help."],
    },
}


def _last_assistant_text(history) -> str:
    for m in reversed(history or []):
        if isinstance(m, dict) and m.get("role") == "assistant":
            content = m.get("content", [])
            if isinstance(content, str):
                return content
            return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def detect_smalltalk(query: str, history=None) -> tuple[str, str] | None:
    """Return (category, reply) if the WHOLE message is small talk, else None.

    The whole message must be made of small-talk phrases, so "hi, what is the
    vacation policy?" is NOT small talk and goes through the normal pipeline.
    """
    norm = normalize(query)
    tokens = norm.split()
    if not tokens or len(tokens) > _MAX_SMALLTALK_TOKENS:
        return None

    cats, i = [], 0
    while i < len(tokens):
        for n in range(min(_MAX_PHRASE_LEN, len(tokens) - i), 0, -1):
            cat = _PHRASES.get(" ".join(tokens[i:i + n]))
            if cat:
                cats.append(cat)
                i += n
                break
        else:
            return None                      # a word that is not small talk
    real = [c for c in cats if c != "filler"]
    if not real:
        return None

    # If the bot just asked the user something (e.g. "what is your name?"),
    # a bare "سلام" / "ok" is probably the ANSWER, not small talk. Only
    # thanks / goodbye are still safe to shortcut then.
    last = _last_assistant_text(history)
    if _QUESTION_MARK.search(last) and not {"farewell", "thanks"} & set(real):
        return None

    if "farewell" in real:
        key = "farewell"
    elif "thanks" in real:
        key = "thanks"
    elif "greeting" in real and "how_are_you" in real:
        key = "greeting_how"
    elif "how_are_you" in real:
        key = "how_are_you"
    elif "greeting" in real:
        key = "salam" if ("سلام عليكم" in norm and not norm.startswith("و")) else "greeting"
    elif "ack" in real:
        key = "ack"
    else:
        key = "neutral"

    lang = "ar" if _HAS_ARABIC.search(query) else "en"
    return key, random.choice(_REPLIES[lang][key])


# --------------------------------------------------------------------------
# Complexity scoring
# --------------------------------------------------------------------------
_RE_HUMAN = re.compile(
    r"(اتكلم|اتحدث|اكلم|اتواصل|تحويل|حولني|وصلني|عايز|عاوز|اريد|ابغي|محتاج)\s+(مع\s+)?(ب)?"
    r"(موظف|شخص|انسان|بشري|ممثل|مندوب|خدمه العملاء|الدعم)"
    r"|\b(human|real person|live agent|live support|representative|talk to (an? )?(agent|person))\b"
    r"|\b(escalate|complaint)\b|\bشكوي\b|\bشكاوي\b"
    r"|(افتح|فتح|انشاء|انشي|سجل|تسجيل)\s+(لي\s+)?(تذكره|شكوي|طلب)"
    r"|\b(open|create|submit|raise)\s+(a\s+)?(new\s+)?(support\s+)?(ticket|complaint)\b"
)
_RE_TICKET_LOOKUP = re.compile(
    r"(تذكره|تذكرتي|ticket|case)\s*(رقم|number|id|no)?\s*[0-9a-z-]*\d[0-9a-z-]*"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-"
    r"|حاله\s+(ال)?تذكر|status of (my )?ticket"
)
_RE_ORDER = re.compile(r"(اوردر|شحنه|طلبي|طلب\s+رقم|order|shipment|tracking|تتبع)")
_RE_ORDER_CTX = re.compile(r"(\d{3,}|status|track|حاله|فين|وين|وصل|تتبع)")
_SQL_ACTION_TOKENS = {"كام", "عدد", "اعرض", "اعرضلي", "اجمالي", "مجموع", "متوسط", "list", "count",
                      "total", "average", "show", "كم"}
_SQL_ACTION_PHRASES = ("how many", "show me", "عدد ال")
_SQL_ENTITY = re.compile(r"(تذكر|تذاكر|ticket|ticketing|الشكاوي)")
# Support-ticket status/time words: a count question about "tickets" only goes to
# SQL when one of these is present, so "كام يوم قبل ما احجز تذكرة طيران" stays RAG.
_SQL_CONTEXT = re.compile(
    r"(مفتوح|معلق|مغلق|مقفول|مفتوحه|معلقه|مغلقه|مقفوله|اليوم|النهارده|امس|الاسبوع|الشهر|"
    r"حاله|حالات|اولويه|عاجل|مفتوحين|"
    r"\b(open|closed|pending|resolved|today|yesterday|week|month|status|priority|urgent|unresolved)\b)")
_REASONING = re.compile(r"(قارن|مقارنه|الفرق|اشرح|لماذا|ليه|why|compare|difference|explain|"
                        r"خطوات|steps|كيف|ازاي|how (do|can|to))")
_MULTI_PART = re.compile(r"(وكمان|و كمان|بالاضافه|ايضا|also|and also|as well as|بعدين|ثم)")
_ASKING_TICKET_INFO = ("رقم الهاتف", "رقم هاتفك", "اسمك", "وصف المشكله", "المشكله التي",
                       "your name", "phone number", "describe the issue")

# (route, level) -> (min_s, max_s). Estimates - calibrate from latency_ms.
ETA_SECONDS = {
    ("smalltalk", "instant"): (0.0, 0.2),
    ("blocked", "instant"): (0.0, 0.2),
    ("rag", "simple"): (1.0, 3.0),        # embedding + pgvector search (+ persona rewrite if custom)
    ("rag", "moderate"): (2.0, 6.0),      # may fall back to the Bedrock tool loop
    ("rag", "complex"): (4.0, 12.0),
    ("tools", "moderate"): (3.0, 10.0),   # 1-3 Bedrock round-trips
    ("tools", "complex"): (5.0, 15.0),
    ("sql", "moderate"): (8.0, 25.0),     # Bedrock + SQL generation + DB + Bedrock
    ("sql", "complex"): (8.0, 25.0),
}


@dataclass
class Analysis:
    score: int
    level: str                       # instant | simple | moderate | complex
    route: str                       # smalltalk | blocked | rag | tools | sql
    eta_seconds: tuple[float, float]
    reasons: list[str] = field(default_factory=list)
    smalltalk_category: str | None = None
    reply: str | None = None

    @property
    def eta_label(self) -> str | None:
        lo, hi = self.eta_seconds
        if hi <= 0.5:
            return None
        return f"حوالي {int(round(lo))}–{int(round(hi))} ثانية" if hi - lo >= 1 else f"حوالي {int(round(hi))} ثانية"

    def to_dict(self) -> dict:
        return {"score": self.score, "level": self.level, "route": self.route,
                "eta_seconds": list(self.eta_seconds), "eta_label": self.eta_label,
                "reasons": self.reasons}


def instant(route: str) -> Analysis:
    return Analysis(0, "instant", route, ETA_SECONDS[(route, "instant")], [route])


def analyze(query: str, history=None, sql_enabled: bool = True) -> Analysis:
    st = detect_smalltalk(query, history)
    if st:
        a = instant("smalltalk")
        a.smalltalk_category, a.reply = st
        return a

    norm = normalize(query)
    tokens = norm.split()
    reasons: list[str] = []
    score = 0

    # --- size of the message
    n = len(tokens)
    pts = 0 if n <= 3 else 5 if n <= 8 else 12 if n <= 20 else 20 if n <= 50 else 25
    if pts:
        score += pts
        reasons.append(f"length:{n}_words")

    # --- several questions / requests in one message
    parts = max(0, len(_QUESTION_MARK.findall(query)) - 1) + len(_MULTI_PART.findall(norm))
    if parts:
        score += min(30, 15 * parts)
        reasons.append(f"multi_part:{parts}")

    # --- reasoning / explanation style
    if _REASONING.search(norm):
        score += 8
        reasons.append("reasoning_words")

    # --- conversation depth
    if len(history or []) >= 4:
        score += 5
        reasons.append("long_conversation")

    # --- intent that needs tools (these skip the direct-RAG shortcut)
    route = "rag"
    last_bot = _last_assistant_text(history)
    if sql_enabled and _SQL_ENTITY.search(norm) and _SQL_CONTEXT.search(norm) and (
            _SQL_ACTION_TOKENS & set(tokens) or any(p in norm for p in _SQL_ACTION_PHRASES)):
        route, score = "sql", score + 45
        reasons.append("structured_data_query")
    elif _RE_TICKET_LOOKUP.search(norm):
        route, score = "tools", score + 30
        reasons.append("ticket_lookup")
    elif _RE_HUMAN.search(norm):
        route, score = "tools", score + 35
        reasons.append("human_escalation_or_ticket")
    elif _RE_ORDER.search(norm) and _RE_ORDER_CTX.search(norm):
        route, score = "tools", score + 25
        reasons.append("order_status")
    elif any(k in last_bot for k in _ASKING_TICKET_INFO):
        route, score = "tools", score + 30
        reasons.append("ticket_info_collection")

    score = min(100, score)
    level = "simple" if score < 20 else "moderate" if score < 45 else "complex"
    if route != "rag" and level == "simple":
        level = "moderate"
    eta = ETA_SECONDS.get((route, level)) or ETA_SECONDS[(route, "moderate")]
    return Analysis(score, level, route, eta, reasons)
