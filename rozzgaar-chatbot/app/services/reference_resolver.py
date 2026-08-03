import re
from difflib import SequenceMatcher

from app.services.knowledge_base import kb

# Matches course/bundle slugs from URLs like:
#   https://rozzgaar.in/applicant/course-content?slug=edp
#   https://rozzgaar.in/courses/edp
#   https://rozzgaar.in/bundles/some-bundle
_SLUG_QUERY_RE = re.compile(r"[?&]slug=([\w-]+)", re.IGNORECASE)
_SLUG_PATH_RE = re.compile(r"/(?:courses|bundles)/([\w-]+)", re.IGNORECASE)

# Any pasted URL at all - used to match against indexed static pages,
# whose slug in the knowledge base IS the full page URL.
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

_FUZZY_MIN_SCORE = 0.55


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").split("#")[0]


def extract_slug_from_url(text: str) -> str | None:
    """Pulls a course/bundle slug out of a pasted Rozzgaar URL. Returns
    None if no course/bundle-style slug pattern is found (e.g. a plain
    marketing page URL won't match - see match_page_url for that)."""
    match = _SLUG_QUERY_RE.search(text) or _SLUG_PATH_RE.search(text)
    return match.group(1) if match else None


def match_page_url(text: str) -> str | None:
    """If the message contains a URL that matches one of the scraped
    static pages (About, Refund Policy, etc.), return that page's slug
    (its own URL, as stored by scrape_static_pages()). Matches loosely
    on the normalized URL so trailing slashes/fragments don't matter."""
    found_urls = [_normalize_url(u) for u in _URL_RE.findall(text)]
    if not found_urls:
        return None

    page_slugs = {slug: _normalize_url(slug) for slug, doc in kb.full_docs.items() if doc.source == "page"}
    for raw_slug, normalized in page_slugs.items():
        if normalized in found_urls:
            return raw_slug
    return None


def fuzzy_match_any(text: str) -> str | None:
    """Falls back to matching a course/bundle/page by title when the user
    names it in plain text instead of pasting a URL/slug, e.g.
    'read me chapter 1 of EDP' or 'summarize the refund policy page'.
    Works against whatever is currently indexed, so it generalizes to
    every course and page without hardcoding."""
    text_lower = text.lower()
    best_slug, best_score = None, 0.0

    for slug, doc in kb.full_docs.items():
        title_lower = doc.title.lower()

        if title_lower in text_lower or (doc.source != "page" and slug.lower() in text_lower):
            return slug  # direct substring hit - no need to go further

        score = SequenceMatcher(None, title_lower, text_lower).ratio()
        if score > best_score:
            best_slug, best_score = slug, score

    return best_slug if best_score >= _FUZZY_MIN_SCORE else None


def resolve_reference(text: str) -> str | None:
    """Single entry point: pasted course/bundle slug -> pasted page URL ->
    fuzzy title match (course, bundle, or page). Returns a slug usable
    with kb.get_full_doc(), or None if nothing in the message points to
    anything specific that's currently indexed."""
    return extract_slug_from_url(text) or match_page_url(text) or fuzzy_match_any(text)