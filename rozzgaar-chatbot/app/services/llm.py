import json
import logging
from functools import lru_cache

from groq import Groq

from app.config import settings

logger = logging.getLogger(__name__)

_client = Groq(api_key=settings.groq_api_key)

_LANG_NAME = {"en": "English", "hi": "Hindi (Devanagari script)"}

# Process-local cache: many different students hit "read module 2 in
# Hindi" / "summarize this" / etc. for the exact same content, and none
# of that changes between requests, so caching by the call's own inputs
# skips a repeat Groq call (and its cost + latency) entirely on a hit.
# Caveats worth knowing:
#   - It's in-memory per worker process - resets on restart/redeploy, and
#     isn't shared across multiple uvicorn/gunicorn workers if you run more
#     than one. Fine for a single-process dev/staging setup like this one;
#     swap for Redis (or similar) behind the same function signatures if
#     you scale to multiple workers.
#   - It does NOT know when course content changes upstream - if a module's
#     text is edited on the Rozzgaar side, a stale cached translation/
#     summary can keep being served until this process restarts. Bump
#     _CACHE_MAXSIZE's neighboring functions' cache with .cache_clear()
#     (e.g. from an admin endpoint or content-refresh hook) if that's a
#     concern for you.
_CACHE_MAXSIZE = 256


def _complete(system: str, user: str, temperature: float = 0.3, max_tokens: int = 700) -> str:
    resp = _client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _cached_answer(question: str, context_chunks: tuple[str, ...], language: str) -> str:
    lang_name = _LANG_NAME.get(language, "English")
    context = "\n\n---\n\n".join(context_chunks) if context_chunks else "No matching content was found."
    system = (
        "You are the official assistant for Rozzgaar (rozzgaar.in), a skills training and "
        "certification platform. Answer ONLY using the CONTEXT provided - never invent course "
        "names, prices, or policies.\n\n"
        "The CONTEXT is the course/page the user is currently browsing (plus closely related "
        "material). If the CONTEXT contains the answer - even if it's covered under a specific "
        "module/chapter - answer the question directly and completely right here using that "
        "content. Do NOT tell the user to go open a module, section, or page for information "
        "that's already sitting in the CONTEXT; that just makes them do the reading themselves. "
        "Only mention a module/chapter by name if the user asks where something is covered, not "
        "as a substitute for answering.\n\n"
        "If the CONTEXT does not contain the answer (the question is about something outside "
        "this course/page), say you don't have that information here and tell the user to visit "
        "the relevant course or the courses page for it - don't try to answer from outside "
        "knowledge.\n\n"
        f"Reply in {lang_name}. Keep answers concise and friendly."
    )
    user = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
    return _complete(system, user)


def answer_with_context(question: str, context_chunks: list[str], language: str) -> str:
    # lru_cache needs hashable args, so tuple-ify the chunk list - the exact
    # same question against the exact same retrieved chunks (common for
    # popular FAQ-style questions) then hits the cache instead of the API.
    return _cached_answer(question, tuple(context_chunks), language)


def _word_count_of(text: str) -> int:
    return len(text.split())


@lru_cache(maxsize=_CACHE_MAXSIZE)
def summarize(text: str, length: str, language: str, title: str | None = None,
              word_count: int | None = None) -> str:
    lang_name = _LANG_NAME.get(language, "English")
    if word_count:
        # An explicit target (e.g. "summarize in 100 words" / "summary in
        # 50 words") always wins over the generic short/long modes.
        low, high = max(5, word_count - 15), word_count + 15
        instruction = (
            f"Write a summary of EXACTLY about {word_count} words (stay within {low}-{high} words - "
            "do not go noticeably over or under). Even at this length, cover every important concept, "
            "point, and takeaway from the content - do not skip a major topic just to hit the word "
            "count; instead compress each topic to a phrase."
        )
    elif length == "short":
        low, high = 100, 150
        instruction = (
            f"Write a summary of {low}-{high} words that covers ALL the important concepts, points, "
            "and takeaways from the content - don't skip any major topic. Use short sentences or "
            "bullet points, prioritizing completeness within that word range."
        )
    else:
        low, high = 200, 300
        instruction = (
            f"Write a LONG, structured summary ({low}-{high} words) that covers every important "
            "concept in the content. Use short paragraphs or bullet points covering: what it is, "
            "who it's for, what's covered (list every major topic/module), and the outcome/benefit."
        )
    system = (
        "You are the Rozzgaar website assistant. Summarize the given page/course content "
        f"faithfully - do not invent facts, prices, or claims not present in the text. Do not be "
        f"overly brief - use the full word range you're given below. Reply in {lang_name}."
    )
    heading = f"TITLE: {title}\n" if title else ""
    user = f"{heading}CONTENT:\n{text}\n\n{instruction}"
    # Scale the token budget for larger targets so the model isn't cut off
    # mid-summary (roughly 3 tokens/word, with headroom).
    target_words = word_count or high
    max_tokens = max(600, min(1600, target_words * 3))
    summary = _complete(system, user, temperature=0.2, max_tokens=max_tokens)

    # Models don't always hit a word target on the first try (usually by
    # coming in short). If the result falls outside the [low, high] range
    # (whether that came from an explicit word_count or the default
    # 100-150/200-300 ranges above), ask again with the actual vs. target
    # range spelled out - retried up to twice, since a single retry can
    # still undershoot on a stubborn response.
    target_label = f"{word_count} words" if word_count else f"{low}-{high} words"
    for _ in range(2):
        actual = _word_count_of(summary)
        if low <= actual <= high:
            break
        direction = "expand" if actual < low else "shorten"
        correction = (
            f"{user}\n\nYour previous attempt was {actual} words; the target is {target_label}. "
            f"{direction.capitalize()} the summary (same content, same {lang_name}) to land within "
            f"{low}-{high} words. If expanding, add more explanation/context for the concepts already "
            "in your summary rather than repeating the same points - do not drop any important concept."
        )
        summary = _complete(system, correction, temperature=0.15, max_tokens=max_tokens)

    return summary


_TRANSLATE_CHUNK_WORDS = 500  # keeps each Groq call's input/output safely within its token limits


@lru_cache(maxsize=_CACHE_MAXSIZE)
def translate(text: str, language: str) -> str:
    """Faithful translation (not a summary) - used for reading page/module
    text aloud in the requested language before it goes to TTS. Long text is
    chunked internally (see _TRANSLATE_CHUNK_WORDS) so a full course/module
    reading isn't cut short by a single completion's output-token limit -
    the whole page/module gets translated and read, not a partial excerpt."""
    if language == "en":
        return text
    words = text.split()
    if len(words) <= _TRANSLATE_CHUNK_WORDS:
        return _translate_chunk(text, language)

    # Split on paragraph boundaries (course text is tagged with "\n\n## "
    # headings by the widget) and pack them into chunks up to the word
    # limit, so each Groq call stays comfortably within its limits while
    # keeping headings/paragraphs intact instead of cutting mid-sentence.
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for para in paragraphs:
        para_words = len(para.split())
        if current and current_words + para_words > _TRANSLATE_CHUNK_WORDS:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
        current.append(para)
        current_words += para_words
    if current:
        chunks.append("\n\n".join(current))

    return "\n\n".join(_translate_chunk(chunk, language) for chunk in chunks)


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _translate_chunk(text: str, language: str) -> str:
    lang_name = _LANG_NAME.get(language, "English")
    system = (
        "You translate text for the Rozzgaar website assistant. Translate the given text into "
        f"natural, conversational, spoken {lang_name}. Do not summarize, add, or omit information - "
        "translate faithfully. Output ONLY the translated text, no commentary, no quotation marks."
    )
    max_tokens = max(800, min(2000, len(text.split()) * 3))
    return _complete(system, text, temperature=0.1, max_tokens=max_tokens)


@lru_cache(maxsize=_CACHE_MAXSIZE)
def generate_suggested_questions(context_text: str, language: str, count: int = 5) -> list[dict]:
    lang_name = _LANG_NAME.get(language, "English")
    system = (
        "You are the Rozzgaar website assistant. Based on the given content, propose sample "
        "questions a prospective student might ask, with short accurate answers grounded only "
        f"in the content. Reply in {lang_name}. "
        "Respond with ONLY a JSON array, no markdown, no commentary, in this exact shape: "
        '[{"question": "...", "answer": "..."}]'
    )
    user = f"CONTENT:\n{context_text}\n\nGenerate exactly {count} question/answer pairs."
    raw = _complete(system, user, temperature=0.4, max_tokens=800)
    return _safe_parse_qa(raw)


def _safe_parse_qa(raw: str) -> list[dict]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1) if cleaned.startswith("json\n") else cleaned
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [
                {"question": item.get("question", "").strip(), "answer": item.get("answer", "").strip()}
                for item in data if isinstance(item, dict)
            ]
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Failed to parse suggested-questions JSON: %s | raw=%s", exc, raw[:200])
    return []