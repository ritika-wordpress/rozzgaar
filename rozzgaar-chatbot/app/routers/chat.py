from typing import NamedTuple

from fastapi import APIRouter, Request

from app.limiter import limiter
from app.models.schemas import ChatRequest, ChatResponse, SourceRef
from app.routers.module_read import _find_module, _flatten_modules, _module_text
from app.services import llm
from app.services.content_fetcher import fetch_course_contents
from app.services.intent import detect_intent, extract_module_query, extract_summary_word_count
from app.services.knowledge_base import kb
from app.services.language import resolve_language
from app.services.reference_resolver import match_page_url, resolve_reference
from app.services.section_finder import extract_heading_query, find_section

router = APIRouter(prefix="/chat", tags=["chat"])


_MIN_LIVE_CONTENT_CHARS = 40  # ignore near-empty DOM captures (loading states, blank pages)
# Only applied when live content is actually going INTO the LLM (summarize /
# suggestions / plain Q&A context) - those calls need a bounded prompt. A
# "read this page" request never hits the LLM for English text (it's echoed
# straight back), so it must NOT be capped here or long pages would get cut
# off mid-sentence instead of being read start to finish.
_MAX_LIVE_CONTENT_CHARS_FOR_LLM = 20000


class ResolvedContent(NamedTuple):
    """Whatever we decided the user is 'looking at' for this turn - either
    a pre-indexed doc (course/bundle/static page) or the live DOM text the
    widget captured off the page it's embedded on right now."""
    text: str
    title: str
    url: str | None
    is_live: bool


def _resolve_live_content(page_url: str | None, page_content: str | None) -> ResolvedContent | None:
    """Keeps the FULL live page text - no truncation here. Callers that feed
    this into the LLM (summarize/suggestions/QA) are responsible for capping
    what they send via _for_llm(); a "read this page" request instead reads
    this text back verbatim, start to finish."""
    text = (page_content or "").strip()
    if len(text) < _MIN_LIVE_CONTENT_CHARS:
        return None
    text = " ".join(text.split())
    title = "this page"
    return ResolvedContent(text=text, title=title, url=page_url, is_live=True)


def _for_llm(text: str) -> str:
    """Bounds text right before it's sent to the LLM (summarize/suggestions/
    QA context). Never used on the path that reads content back to the user."""
    return text[:_MAX_LIVE_CONTENT_CHARS_FOR_LLM]


def _resolve_content(message: str, page_url: str | None, page_content: str | None) -> tuple[str | None, ResolvedContent | None]:
    """Single entry point deciding what content a 'read/summarize/suggest'
    request should use, in priority order:

      1. A course/bundle/static page explicitly named or linked in the
         message itself (resolve_reference) - the user asked about
         something specific, so that always wins even if it differs from
         whatever page they happen to be on.
      2. The LIVE content of the page the widget is embedded on right now
         (page_content, captured fresh from the rendered DOM after login).
         This is what makes "read this page" / "summarize this" work on
         ANY page - dashboards, profile pages, anything client-rendered -
         without it needing to be pre-scraped or indexed ahead of time.
      3. A pre-indexed static page whose URL matches page_url, for the
         case where the widget hasn't sent page_content (e.g. an older
         embed snippet) but we do have that page scraped already.

    Returns (slug, live) - slug is set for (1)/(3) i.e. anything backed by
    the knowledge base, live is set for (2). Exactly one (or neither, if
    nothing resolves) will be non-None."""
    slug = resolve_reference(message)
    if slug:
        return slug, None

    live = _resolve_live_content(page_url, page_content)
    if live:
        return None, live

    if page_url:
        slug = match_page_url(page_url)
        if slug:
            return slug, None

    return None, None


def _read_full_doc(slug: str, language: str) -> ChatResponse:
    """Reads back a static page (or a course/bundle with no specific
    chapter mentioned) using its full indexed text."""
    doc = kb.get_full_doc(slug)
    if not doc or not doc.text.strip():
        reply = ("I don't have content indexed for that page yet."
                  if language == "en" else
                  "मेरे पास अभी उस पेज की जानकारी उपलब्ध नहीं है।")
        return ChatResponse(reply=reply, language=language, sources=[], suggested_questions=[])

    return _text_to_read_response(doc.text, language, SourceRef(title=doc.title, url=doc.url))


def _text_to_read_response(text: str, language: str, source: SourceRef | None) -> ChatResponse:
    # No truncation: a "read this page/module" request should read the
    # entire course content start to finish, not a partial excerpt. Very
    # long text is still handled safely - llm.translate() chunks internally
    # so translated readings don't get cut off either.
    if language != "en":
        text = llm.translate(text, language)

    return ChatResponse(reply=text, language=language,
                         sources=[source] if source else [],
                         suggested_questions=[])


def _not_found_prefix(heading_query: str, language: str) -> str:
    return (f"I couldn't find a section called \"{heading_query}\" here - reading the full thing instead.\n\n"
            if language == "en" else
            f"मुझे यहाँ \"{heading_query}\" नाम का सेक्शन नहीं मिला - पूरा पढ़ रहा हूँ।\n\n")


def _handle_read(message: str, slug: str | None, live: ResolvedContent | None, language: str) -> ChatResponse:
    heading_query = extract_heading_query(message)

    if not slug:
        # No indexed doc matched - fall back to whatever live page content
        # was resolved (may be None, handled by _text_to_read_response's
        # caller below via the "nothing to read" branch in build_chat_response).
        source = SourceRef(title=live.title, url=live.url) if live and live.url else None
        text = live.text if live else ""
        if heading_query and live:
            section = find_section(live.text, heading_query)
            if section:
                return _text_to_read_response(section, language, source)
            response = _text_to_read_response(text, language, source)
            response.reply = _not_found_prefix(heading_query, language) + response.reply
            return response
        return _text_to_read_response(text, language, source)

    doc = kb.get_full_doc(slug)
    module_query = extract_module_query(message)

    # Only courses/bundles have chapters to look up, and only when the
    # message actually names one (a bare number/title was extracted).
    wants_specific_module = module_query.strip().lower() != message.strip().lower()
    if doc and doc.source in ("course", "bundle") and wants_specific_module:
        contents = fetch_course_contents(slug)
        modules = _flatten_modules(contents) if contents else []
        module = _find_module(modules, module_query) if modules else None

        if module:
            text = _module_text(module)
            not_found_note = ""
            if heading_query:
                section = find_section(text, heading_query)
                if section:
                    text = section
                else:
                    not_found_note = _not_found_prefix(heading_query, language)
            if language != "en":
                text = llm.translate(text, language)
            return ChatResponse(reply=not_found_note + text, language=language,
                                 sources=[SourceRef(title=doc.title, url=doc.url)],
                                 suggested_questions=[])
        # fall through to reading the full doc if the named module wasn't found

    if heading_query and doc:
        section = find_section(doc.text, heading_query)
        if section:
            return _text_to_read_response(section, language, SourceRef(title=doc.title, url=doc.url))

    return _read_full_doc(slug, language)


def _handle_summarize(message: str, slug: str | None, live: ResolvedContent | None, chunks, language: str) -> ChatResponse:
    doc = kb.get_full_doc(slug) if slug else None
    if doc:
        text, title, sources = doc.text, doc.title, [SourceRef(title=doc.title, url=doc.url)]
    elif live:
        text, title = live.text, live.title
        sources = [SourceRef(title=live.title, url=live.url)] if live.url else []
    else:
        text, title, sources = "\n".join(c.text for c in chunks), None, []

    if not text.strip():
        reply = ("I don't have enough content to summarize that."
                  if language == "en" else
                  "मेरे पास उसका सारांश देने के लिए पर्याप्त जानकारी नहीं है।")
        return ChatResponse(reply=reply, language=language, sources=[], suggested_questions=[])

    # Honors explicit requests like "summarize in 100 words" / "give summary
    # in 50 words" typed straight into chat; falls back to the normal short
    # summary when no word count was requested.
    word_count = extract_summary_word_count(message)
    summary = llm.summarize(_for_llm(text), "short", language, title=title, word_count=word_count)
    return ChatResponse(reply=summary, language=language, sources=sources, suggested_questions=[])


def _handle_suggestions(slug: str | None, live: ResolvedContent | None, chunks, language: str) -> ChatResponse:
    doc = kb.get_full_doc(slug) if slug else None
    if doc:
        context_text, sources = doc.text, [SourceRef(title=doc.title, url=doc.url)]
    elif live:
        context_text = live.text
        sources = [SourceRef(title=live.title, url=live.url)] if live.url else []
    else:
        context_text, sources = "\n".join(c.text for c in chunks), []

    qa = llm.generate_suggested_questions(_for_llm(context_text), language, count=3)
    questions = [item["question"] for item in qa if item.get("question")]

    reply = ("Here are some questions you could ask:"
              if language == "en" else
              "यहाँ कुछ सवाल हैं जो आप पूछ सकते हैं:")
    return ChatResponse(reply=reply, language=language, sources=sources, suggested_questions=questions)


def build_chat_response(
    message: str,
    requested_language: str = "auto",
    page_url: str | None = None,
    page_content: str | None = None,
) -> ChatResponse:
    """Shared pipeline used by both the text /chat endpoint and the
    /voice/chat endpoint. Routes to reading, summarizing, or
    suggested-questions when the message asks for one of those; falls
    back to general RAG Q&A otherwise. Works for any course/page already
    indexed - no per-course hardcoding.

    page_url is the page the widget is currently embedded on (sent by the
    frontend on every request). page_content is that page's live, rendered
    text - captured by the widget straight from the DOM, after login and
    after any client-side JS has finished rendering. Together these let
    "read it" / "summarize this" work on literally any page the logged-in
    user is looking at, not just pages we've pre-scraped and indexed.

    Resolution order (see _resolve_content): a course/page named directly
    in the message > the live page_content the widget just sent > a
    pre-indexed static page matching page_url, as a fallback for older
    widget embeds that don't send page_content yet."""
    language = resolve_language(requested_language, message)
    intent = detect_intent(message)

    needs_page_content = intent in ("read_content", "summarize", "suggestions")
    slug: str | None = None
    live: ResolvedContent | None = None
    if needs_page_content:
        slug, live = _resolve_content(message, page_url, page_content)
    else:
        # Plain Q&A still benefits from a named reference (e.g. "does the
        # EDP course cover X?"), just not from the live page fallback -
        # general questions are answered from the indexed knowledge base.
        slug = resolve_reference(message)

    chunks = kb.retrieve(message, top_k=5)

    if intent == "read_content":
        if slug or live:
            return _handle_read(message, slug, live, language)
        reply = ("I don't have content to read right now - try opening a course page, "
                  "or ask me something specific."
                  if language == "en" else
                  "अभी पढ़ने के लिए मेरे पास कोई जानकारी नहीं है - कोई कोर्स पेज खोलें या कुछ खास पूछें।")
        return ChatResponse(reply=reply, language=language, sources=[], suggested_questions=[])
    if intent == "summarize":
        return _handle_summarize(message, slug, live, chunks, language)
    if intent == "suggestions":
        return _handle_suggestions(slug, live, chunks, language)

    reply = llm.answer_with_context(message, [c.text for c in chunks], language)

    seen = set()
    sources = []
    for c in chunks:
        if c.slug in seen:
            continue
        seen.add(c.slug)
        sources.append(SourceRef(title=c.title, url=c.url))

    suggestions: list[str] = []
    if chunks:
        context_text = "\n".join(c.text for c in chunks[:3])
        qa = llm.generate_suggested_questions(context_text, language, count=3)
        suggestions = [item["question"] for item in qa if item.get("question")]

    return ChatResponse(
        reply=reply,
        language=language,
        sources=sources,
        suggested_questions=suggestions,
    )


@router.post("/", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    return build_chat_response(payload.message, payload.language, payload.page_url, payload.page_content)
