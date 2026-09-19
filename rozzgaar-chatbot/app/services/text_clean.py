"""Strips emoji/icon/decorative-symbol characters (📘 📦 ✓ ⭐ 🔊 etc.) out of
text that will eventually be spoken by TTS. These are common in scraped UI
text (course cards, badges, buttons) but have no sensible pronunciation -
browsers/TTS engines either skip them silently (fine) or, worse, read out
their Unicode name ("check mark button") which sounds broken to a listener.

Used in two places, both defense-in-depth for the same problem:
  1. At ingestion (chat.py's _resolve_live_content, module_read.py) - so
     these characters never even reach the LLM as context, which also
     quietly shrinks the prompt (fewer tokens = faster + cheaper).
  2. At output (llm.py's translate/summarize/generate_suggested_questions)
     - a safety net in case the model itself echoes a decorative symbol
       back that wasn't in the source (rare, but happens with bullet-style
       formatting).

Deliberately does NOT strip: normal punctuation, currency signs (₹ is in
the Currency Symbols block, not touched), Devanagari script, or plain
arrows/dashes used as actual sentence punctuation - only pictographic/
dingbat/technical-symbol Unicode ranges are removed.
"""
import re

_DECORATIVE_SYMBOLS_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # misc pictographs, emoticons, transport, supplemental symbols A/B
    "\U00002600-\U000026FF"  # misc symbols (☀ ☂ ⚡ ☑ etc.)
    "\U00002700-\U000027BF"  # dingbats (✓ ✔ ✗ ➤ ✂ etc.)
    "\U0001F1E6-\U0001F1FF"  # regional indicators / flags
    "\U00002300-\U000023FF"  # misc technical (⌚ ⏰ ⏳ etc.)
    "\U00002B00-\U00002BFF"  # misc symbols and arrows (⭐ ➡ etc.)
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0001F000-\U0001F0FF"  # mahjong / playing cards
    "\U0000200D"              # zero-width joiner (glues combined emoji together)
    "]+",
    flags=re.UNICODE,
)


def strip_decorative_symbols(text: str) -> str:
    """Removes emoji/icon characters and collapses whatever extra
    whitespace they leave behind. Safe to call on already-clean text
    (no-op) and on None/empty strings."""
    if not text:
        return text
    cleaned = _DECORATIVE_SYMBOLS_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_MD_RULES = [
    (re.compile(r"^\s*[-*_=]{3,}\s*$", re.MULTILINE), ""),                 # --- horizontal rules
    (re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE), ""),                  # # headings
    (re.compile(r"^\s{0,3}>\s?", re.MULTILINE), ""),                       # > blockquotes
    (re.compile(r"(\*{1,3}|_{2,3}|~~)(?=\S)(.+?)(?<=\S)\1"), r"\2"),     # **bold** *italic* __bold__ ~~strike~~
    (re.compile(r"`+([^`]*)`+"), r"\1"),                                   # `code`
    (re.compile(r"^\s*[-*+\u2022]\s+", re.MULTILINE), ""),                 # - bullets
    (re.compile(r"\*{2,}"), ""),                                           # any stray ** left over
]

# A trailing "(120 words)" / "[about 100 words]" / "Word count: 120" note the
# model sometimes adds to a summary - users shouldn't be told how long the
# answer is.
_WORD_COUNT_NOTE_RES = [
    re.compile(r"\s*[\(\[]\s*(?:about\s+|approximately\s+|approx\.?\s+|~)?\d{1,4}\s*(?:words?|\u0936\u092c\u094d\u0926(?:\u094b\u0902)?)\s*[\)\]]", re.IGNORECASE),
    re.compile(r"^\s*(?:word\s*count|\u0936\u092c\u094d\u0926\s*\u0938\u0902\u0916\u094d\u092f\u093e)\s*[:\-]\s*\d+.*$", re.IGNORECASE | re.MULTILINE),
]


def clean_reply_text(text: str) -> str:
    """Final pass for text the LLM writes for the user (chat answers and
    summaries): removes markdown leftovers (** # --- bullets etc.) and any
    "(N words)" note, so replies are plain summarised text. Safe on
    already-clean text and on None/empty strings."""
    if not text:
        return text
    cleaned = text
    for rx, repl in _MD_RULES:
        cleaned = rx.sub(repl, cleaned)
    for rx in _WORD_COUNT_NOTE_RES:
        cleaned = rx.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()