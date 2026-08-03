import re

# Devanagari unicode block covers Hindi script
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Someone typing in English/Latin script but asking for the OTHER
# language - "answer in Hindi", "hindi mein batao", "hindi me bolo",
# "reply in english", "english mein". Checked before falling back to
# script-only detection, so an explicit request always wins even when
# the rest of the message is plain English.
_ASK_FOR_HINDI_RE = re.compile(r"\b(?:in\s+hindi|hindi\s+m(?:ei|e)n|hindi\s+me|hindi\s+language)\b", re.IGNORECASE)
_ASK_FOR_ENGLISH_RE = re.compile(r"\b(?:in\s+english|english\s+m(?:ei|e)n|english\s+me|english\s+language)\b", re.IGNORECASE)


def detect_language(text: str) -> str:
    """Return 'hi' if the text contains Devanagari script or an explicit
    English-typed request for Hindi, else 'en'.

    This is a lightweight heuristic good enough for Hindi-in-Devanagari vs
    English, plus the common "answer in Hindi"/"hindi mein" phrasing.
    Romanized Hindi sentences that DON'T explicitly name the language
    ("aap kaise ho") will still be detected as English - if that matters
    for your users, swap this for a proper model (e.g. `fasttext` lid.176
    or `langdetect`) later without changing any other module, since every
    caller only imports detect_language().
    """
    if not text or not text.strip():
        return "en"
    if _ASK_FOR_HINDI_RE.search(text):
        return "hi"
    if _ASK_FOR_ENGLISH_RE.search(text):
        return "en"
    return "hi" if _DEVANAGARI_RE.search(text) else "en"


def resolve_language(requested: str, message: str) -> str:
    """Resolve the "auto" language option against the actual message text."""
    if requested in ("en", "hi"):
        return requested
    return detect_language(message)
