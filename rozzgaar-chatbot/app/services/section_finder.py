"""Lets 'read this page' target one heading/section/paragraph instead of
always reading the whole page.

Pairs with the widget's extractPageContent(), which prefixes every
heading with a '## ' marker on its own line before flattening the page
to text (see static/embed.js). That gives us a cheap, reliable split
point here without needing to parse HTML on the backend.
"""
import difflib
import re

# Strips a leading "read"/"open"/"show me"/"please read the" etc. so the
# query-extraction regexes below don't accidentally swallow the verb
# itself into the captured heading name.
_LEAD_IN_RE = re.compile(
    r"^\s*(?:please\s+)?(?:read out loud|read aloud|read out|read|open|show me|show)\s+(?:me\s+)?(?:the\s+)?",
    re.IGNORECASE,
)

# Quoted text always wins: `read "Eligibility Criteria"` / read 'the FAQ'.
_QUOTED_RE = re.compile(r"[\"'\u2018\u2019\u201c\u201d]([^\"'\u2018\u2019\u201c\u201d]{2,80})[\"'\u2018\u2019\u201c\u201d]")

# "Eligibility Criteria heading/section/paragraph/part" (lead-in already stripped)
_QUERY_BEFORE_KEYWORD_RE = re.compile(
    r"\b(?:the\s+)?([\w][\w\s,&'-]{1,60}?)\s+(?:heading|section|paragraph|part)\b", re.IGNORECASE
)
# "heading/section/paragraph/part on/about/called/titled/named X"
_KEYWORD_BEFORE_QUERY_RE = re.compile(
    r"\b(?:heading|section|paragraph|part)\b\s*(?:on|about|called|titled|named|:)?\s*[\"']?([^\"'.?!\n]{2,80})",
    re.IGNORECASE,
)

_FILLER_ONLY = {"this", "that", "the", "a", "it", "here"}
_SECTION_SPLIT_RE = re.compile(r"\n##\s+")
_MATCH_THRESHOLD = 0.55  # fuzzy-match floor below which we treat it as "not found"


def extract_heading_query(message: str) -> str | None:
    """Pulls out the heading/section/paragraph name the user wants read
    back - e.g. "read the Eligibility Criteria heading" -> "Eligibility
    Criteria". Returns None when the message doesn't name a specific
    section, so callers fall back to reading the whole page/doc as before."""
    quoted = _QUOTED_RE.search(message)
    if quoted:
        candidate = quoted.group(1).strip()
        if candidate:
            return candidate

    remainder = _LEAD_IN_RE.sub("", message, count=1)

    before = _QUERY_BEFORE_KEYWORD_RE.search(remainder)
    if before:
        candidate = before.group(1).strip(" .,:-")
        if candidate and candidate.lower() not in _FILLER_ONLY:
            return candidate

    after = _KEYWORD_BEFORE_QUERY_RE.search(remainder)
    if after:
        candidate = after.group(1).strip(" .,:-")
        if candidate and candidate.lower() not in _FILLER_ONLY:
            return candidate

    return None


def find_section(text: str, heading_query: str) -> str | None:
    """Given text with '## Heading' markers, returns 'Heading\\nBody' for
    whichever section's heading best matches heading_query. Returns None
    if the text has no heading markers at all, or nothing matches closely
    enough - callers should fall back to reading the full text either way."""
    if not text or "\n## " not in f"\n{text}":
        return None

    parts = _SECTION_SPLIT_RE.split(text)
    query = heading_query.strip().lower()
    if not query:
        return None

    best_body: str | None = None
    best_score = 0.0
    for part in parts[1:]:  # parts[0] is whatever came before the first heading
        heading_line, _, body = part.partition("\n")
        heading_line = heading_line.strip()
        if not heading_line:
            continue
        h_lower = heading_line.lower()
        # Exact substring either direction counts as a full match; otherwise
        # fall back to a fuzzy ratio so small typos/wording differences
        # ("eligibility" vs "eligibility criteria") still resolve.
        score = 1.0 if (query in h_lower or h_lower in query) else difflib.SequenceMatcher(None, query, h_lower).ratio()
        if score > best_score:
            best_score = score
            best_body = f"{heading_line}\n{body.strip()}"

    return best_body if best_score >= _MATCH_THRESHOLD else None
