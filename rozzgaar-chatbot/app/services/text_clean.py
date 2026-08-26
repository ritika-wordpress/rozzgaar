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