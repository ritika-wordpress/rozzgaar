import re
from typing import Literal

Intent = Literal["read_content", "summarize", "suggestions", "qa"]

_MODULE_RE = re.compile(r"(?:chapter|module|lesson)\s*(\d+)?", re.IGNORECASE)
_READ_WORDS = ("read", "open", "show me", "read out", "read aloud")
_SUMMARY_WORDS = ("summar", "overview", "tl;dr", "in short", "key points")
_SUGGEST_WORDS = (
    "sample question", "suggest question", "faq", "what can i ask", "example question",
    "practice question", "mock question", "quiz me", "test me", "ask me question",
)
# Catches free-form phrasings like "generate some questions from this content",
# "give me a few questions on this", "can you make questions about this page" -
# i.e. any sentence that talks about (generate|give|create|make|prepare) ... question(s).
_SUGGEST_RE = re.compile(
    r"\b(generate|give|create|make|prepare|come up with|list)\b.{0,40}\bquestions?\b", re.IGNORECASE
)
# Matches an explicit word target in phrasings like "summarize in 100 words",
# "give summary in 50 words", "100 word summary".
_WORD_COUNT_RE = re.compile(r"(\d{1,4})\s*[-]?\s*words?\b", re.IGNORECASE)


# ---- "give me N MCQs" support -------------------------------------------
# The most MCQs one request will return. Higher asks are clamped (and the
# reply says so) so a single message can't fan out into a huge, slow LLM job.
MAX_QUESTIONS = 20

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_COUNT_TARGET = r"(?:m\.?\s?c\.?\s?qs?|questions?|quiz(?:zes)?|multiple[\s-]?choice|\u092a\u094d\u0930\u0936\u094d\u0928|\u0938\u0935\u093e\u0932)"
# "10 mcqs", "10 multiple choice questions", "ten questions"
_COUNT_BEFORE_RE = re.compile(
    rf"(?<![\w.])(\d{{1,3}}|{'|'.join(_NUM_WORDS)})\s*(?:[A-Za-z\-]+\s+){{0,2}}?{_COUNT_TARGET}",
    re.IGNORECASE,
)
# "mcqs: 10", "questions - 5"
_COUNT_AFTER_RE = re.compile(rf"{_COUNT_TARGET}\s*[:=\-x]\s*(\d{{1,3}})\b", re.IGNORECASE)
# "chapter 2 questions" is about chapter 2, not a request for 2 questions
_UNIT_BEFORE_RE = re.compile(
    r"(?:chapter|module|lesson|unit|page|part|section|class|step|\u0905\u0927\u094d\u092f\u093e\u092f|\u092e\u0949\u0921\u094d\u092f\u0942\u0932|\u092a\u093e\u0920)\s*$",
    re.IGNORECASE,
)
_MCQ_WORD_RE = re.compile(r"\bm\.?\s?c\.?\s?qs?\b|\u090f\u092e\s?\u0938\u0940\s?\u0915\u094d\u092f\u0942|multiple[\s-]?choice|\bquiz\b|\u092c\u0939\u0941\u0935\u093f\u0915\u0932\u094d\u092a\u0940\u092f", re.IGNORECASE)
_ASK_VERB_RE = re.compile(
    r"\b(generate|give|create|make|prepare|list|show|need|want|provide|write|send|ask|test|quiz|practice|practise|please|pls)\b"
    r"|\u0926\u094b|\u0926\u0947\u0902|\u0926\u0940\u091c\u093f\u090f|\u092c\u0928\u093e\u0913|\u091a\u093e\u0939\u093f\u090f",
    re.IGNORECASE,
)


def extract_question_count(message: str) -> int | None:
    """How many MCQs/questions the user asked for: '10 mcqs' -> 10,
    'give me five questions' -> 5, 'mcqs: 8' -> 8. None if no number was
    given (the caller then uses its normal default)."""
    for match in _COUNT_BEFORE_RE.finditer(message):
        if _UNIT_BEFORE_RE.search(message[:match.start()]):
            continue
        raw = match.group(1).lower()
        count = _NUM_WORDS.get(raw) or (int(raw) if raw.isdigit() else None)
        if count and count >= 1:
            return count
    match = _COUNT_AFTER_RE.search(message)
    if match:
        count = int(match.group(1))
        if count >= 1:
            return count
    return None


def detect_intent(message: str) -> Intent:
    lower = message.lower()

    # Check suggestions FIRST: it's the most specific signal (explicitly
    # mentions "question"/quiz/faq), whereas the read-content check below
    # matches on a bare "module"/"chapter"/"lesson" mention with no digit
    # required - so "quiz me on chapter 2" or "give me a few questions on
    # this module" would otherwise be misdetected as read_content just for
    # naming the chapter/module, and the suggestion branch would never run.
    if any(w in lower for w in _SUGGEST_WORDS) or _SUGGEST_RE.search(lower):
        return "suggestions"
    # "give me 10 mcqs", "5 questions on this", "mcq please" - but not a
    # plain "what is an MCQ?" (needs a number or a request verb).
    if _MCQ_WORD_RE.search(lower) and (extract_question_count(message) or _ASK_VERB_RE.search(lower)):
        return "suggestions"
    if extract_question_count(message):
        return "suggestions"
    # "read chapter 2", "read this page", "read the about page" all count -
    # a chapter/module number is a bonus signal, not a requirement.
    if any(w in lower for w in _READ_WORDS) or _MODULE_RE.search(lower):
        return "read_content"
    if any(w in lower for w in _SUMMARY_WORDS):
        return "summarize"
    return "qa"


def extract_summary_word_count(message: str) -> int | None:
    """Pulls an explicit word-count target out of the user's own message,
    e.g. 'summarize in 100 words' or 'give summary in 50 words' -> 100 / 50.
    Returns None when no explicit count was requested, in which case the
    existing short/long default behaviour is unchanged."""
    match = _WORD_COUNT_RE.search(message)
    if not match:
        return None
    try:
        count = int(match.group(1))
    except ValueError:
        return None
    return count if 5 <= count <= 1000 else None


def extract_module_query(message: str) -> str:
    """Pulls out something like 'module 1' / 'chapter 3' to pass into
    the existing _find_module() matcher in module_read.py. Falls back to
    the raw message so free-text titles ('the setup lesson') still work."""
    match = _MODULE_RE.search(message)
    if match and match.group(1):
        unit = "module" if "module" in match.group(0).lower() else \
               "chapter" if "chapter" in match.group(0).lower() else "lesson"
        return f"{unit} {match.group(1)}"
    return message