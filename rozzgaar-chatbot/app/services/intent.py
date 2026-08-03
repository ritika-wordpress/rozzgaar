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