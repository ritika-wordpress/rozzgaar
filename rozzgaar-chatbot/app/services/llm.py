import atexit
import hashlib
import json
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from deep_translator import GoogleTranslator
from deep_translator.exceptions import RequestError, TooManyRequests, TranslationNotFound
from groq import Groq

from app.config import settings
from app.services.text_clean import strip_decorative_symbols

logger = logging.getLogger(__name__)

_client = Groq(api_key=settings.groq_api_key)

_LANG_NAME = {"en": "English", "hi": "Hindi (Devanagari script)"}

# Language codes for deep-translator's GoogleTranslator (the free web-scraping
# endpoint, no API key) - separate from _LANG_NAME above, which is only used
# to build Groq prompts for the Q&A/summarize/suggested-questions functions
# further down. Translation itself no longer goes through Groq at all: no
# reasoning-token budget to run out, no per-minute LLM rate limit, no JSON
# parsing of a model's output. Trade-off: this hits Google's unofficial
# translate.google.com endpoint, which has its own (undocumented) rate
# limiting and can occasionally 429/error under heavy concurrent load - see
# _translate_chunk's retry handling below.
_DT_LANG = {"en": "en", "hi": "hi"}

# --------------------------------------------------------------------------
# Disk-backed cache, shared by course-content summaries, suggested
# questions, AND (see _translate_chunk further down) individual Google
# Translate lookups.
#
# This used to only back summarize()/generate_suggested_questions(); a
# plain @lru_cache handled translation instead, which - per the old comment
# here - only survives for the life of one worker process. That's a much
# bigger deal for translation than for summaries: a "translate this page"
# walk can be a few hundred DOM-node strings, hit by every visitor who
# picks Hindi, and none of it changes until the underlying page copy is
# edited. Routing translation through this same on-disk cache means:
#   - It's a genuine SERVER-side cache: persists across restarts/redeploys
#     (unlike @lru_cache), and is shared across every visitor who hits this
#     backend - not just repeat visits from the same browser, which is all
#     the widget's own client-side localStorage cache can do (see the
#     "server-side cache (shared across all visitors...)" comment in
#     static/embed.js - this is that cache).
#   - Keyed by content hash + params (mirrors app/services/video_transcript
#     .py's cache pattern), so it stays correct automatically if the
#     underlying text changes (new key -> cache miss -> retranslate/
#     regenerate) and stale entries just sit unused rather than serving
#     wrong content.
#   - An in-memory mirror (_response_cache_mem) is loaded from disk once
#     and kept warm after that, so a cache HIT - the overwhelmingly common
#     case once a page's translations exist - is a plain dict lookup, not
#     a JSON re-read+re-parse on every one of a few hundred per-node calls.
#     A write still persists to disk immediately, so nothing is lost if
#     the process restarts right after.
#
# Still not multi-process safe under concurrent writes to the SAME key (a
# duplicate Google Translate/Groq call in that narrow race is harmless -
# one of the two write attempts just wins), and still single-process only
# - swap for Redis (or similar) behind the same _disk_cached signature if
# you scale to multiple uvicorn/gunicorn workers.
# --------------------------------------------------------------------------
_RESPONSE_CACHE_LOCK = threading.Lock()
_response_cache_mem: dict | None = None  # lazily loaded, then kept warm for the life of the process
_response_cache_dirty = False  # True when the in-memory mirror has writes not yet flushed to disk
_response_cache_flush_thread_started = False
_RESPONSE_CACHE_FLUSH_INTERVAL = 2.0  # seconds between background flushes to disk


def _response_cache_path() -> Path:
    p = Path(settings.data_dir) / "llm_response_cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_response_cache() -> dict:
    """Returns the in-memory mirror, loading it from disk once on first
    use. Callers must hold _RESPONSE_CACHE_LOCK."""
    global _response_cache_mem
    if _response_cache_mem is not None:
        return _response_cache_mem
    path = _response_cache_path()
    if not path.exists():
        _response_cache_mem = {}
        return _response_cache_mem
    try:
        _response_cache_mem = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("LLM response cache unreadable (%s), starting fresh.", exc)
        _response_cache_mem = {}
    return _response_cache_mem


def _save_response_cache() -> None:
    """Persists the current in-memory mirror to disk. Callers must hold
    _RESPONSE_CACHE_LOCK."""
    try:
        _response_cache_path().write_text(json.dumps(_response_cache_mem, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to persist LLM response cache: %s", exc)


def _stage_response_cache_write(key: str, value) -> None:
    """Writes `value` into the in-memory mirror under `key` and marks the
    cache dirty for the background thread to flush - does NOT write to
    disk itself. Callers must hold _RESPONSE_CACHE_LOCK.

    This is the fix for a real slowdown: writing the WHOLE cache file to
    disk synchronously on every single miss (the previous version of this
    code) means every one of a "translate this page" walk's few hundred
    first-time nodes re-serializes and rewrites the ENTIRE cache - every
    summary, every suggested-question set, every translation ever cached,
    not just the one new entry - while holding the lock the other worker
    threads are waiting on. The file only grows over time, so this got
    slower the more the site was used, and effectively serialized what
    should have been 4 concurrent Google Translate calls behind that one
    blocking write. Staging the write in memory and flushing on a timer
    instead means the request path only ever does a dict assignment under
    the lock (microseconds), and disk I/O happens in the background,
    batched, regardless of how many misses land in that window."""
    global _response_cache_dirty
    cache = _load_response_cache()
    cache[key] = value
    _response_cache_dirty = True
    _ensure_response_cache_flush_thread()


def _ensure_response_cache_flush_thread() -> None:
    """Starts the background flush thread the first time it's needed.
    Callers must hold _RESPONSE_CACHE_LOCK (called only from
    _stage_response_cache_write above)."""
    global _response_cache_flush_thread_started
    if _response_cache_flush_thread_started:
        return
    _response_cache_flush_thread_started = True
    threading.Thread(target=_response_cache_flush_loop, name="response-cache-flush", daemon=True).start()


def _response_cache_flush_loop() -> None:
    while True:
        time.sleep(_RESPONSE_CACHE_FLUSH_INTERVAL)
        _flush_response_cache_if_dirty()


def _flush_response_cache_if_dirty() -> None:
    global _response_cache_dirty
    with _RESPONSE_CACHE_LOCK:
        if not _response_cache_dirty:
            return
        _save_response_cache()
        _response_cache_dirty = False


# Best-effort flush on a clean process exit (SIGTERM via a graceful uvicorn
# shutdown, normal interpreter exit) so a redeploy right after a burst of
# new translations doesn't lose up to _RESPONSE_CACHE_FLUSH_INTERVAL seconds
# of them. An abrupt kill -9 can still lose that window - acceptable, since
# the worst case is just recomputing a few entries once more later, not
# losing anything that isn't trivially regenerable.
atexit.register(_flush_response_cache_if_dirty)


def _response_cache_key(namespace: str, *parts: object) -> str:
    raw = namespace + "\x1f" + "\x1f".join(repr(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _disk_cached(namespace: str, key_parts: tuple, compute):
    """Return the cached value for (namespace, key_parts) if present on
    disk (via the in-memory mirror), otherwise call compute(), persist the
    result, and return it. Safe across threads (single lock around
    read-modify-write); not multi-process safe under concurrent writes to
    the SAME key, but a duplicate Groq/translate call in that narrow race
    is harmless - it just means one of the two write attempts is what ends
    up persisted."""
    key = _response_cache_key(namespace, *key_parts)
    with _RESPONSE_CACHE_LOCK:
        cache = _load_response_cache()
        if key in cache:
            return cache[key]
    result = compute()
    with _RESPONSE_CACHE_LOCK:
        _stage_response_cache_write(key, result)
    return result


def _complete(system: str, user: str, temperature: float = 0.3, max_tokens: int = 700,
              reasoning_effort: str | None = "low") -> str:
    # groq_model (openai/gpt-oss-20b) is a reasoning model: hidden "thinking"
    # tokens are drawn from the SAME max_tokens budget as the visible answer.
    # On bigger prompts (e.g. a large translate-batch chunk) the model can
    # spend the whole budget reasoning and return an EMPTY message - which
    # then fails JSON parsing downstream. reasoning_effort="low" keeps most
    # of the budget available for actual output on tasks (like translation)
    # that don't need deep reasoning. Only gpt-oss/qwen3 models on Groq
    # accept this param, so skip it silently for anything else.
    # NOTE: this now DEFAULTS to "low" (previously every call site left it
    # at None, so the flag documented above was never actually sent to
    # Groq - the empty-response warnings in the logs were exactly this).
    # Pass reasoning_effort=None explicitly to opt a call out.
    kwargs = {}
    if reasoning_effort and "gpt-oss" in settings.groq_model:
        kwargs["reasoning_effort"] = reasoning_effort
    resp = _client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    content = resp.choices[0].message.content
    finish_reason = resp.choices[0].finish_reason
    if (not content or not content.strip()) and finish_reason == "length":
        # Even with reasoning_effort="low", a big enough prompt can still
        # eat the whole budget on hidden reasoning tokens. One retry with a
        # meaningfully larger budget clears almost all of these rather than
        # silently returning "" to the caller (which upstream turns into a
        # visible failure - a blank summary, an empty suggested-question
        # list, an unanswered chat message).
        retry_tokens = max_tokens * 2
        logger.warning("Groq returned empty content (finish_reason=length, max_tokens=%d) - "
                        "retrying once with max_tokens=%d.", max_tokens, retry_tokens)
        resp = _client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=retry_tokens,
            **kwargs,
        )
        content = resp.choices[0].message.content
        finish_reason = resp.choices[0].finish_reason
        if not content or not content.strip():
            logger.warning("Groq still returned empty content after retry (finish_reason=%s, "
                            "max_tokens=%d).", finish_reason, retry_tokens)
    return (content or "").strip()


def _cached_answer_impl(question: str, context_chunks: tuple[str, ...], language: str) -> str:
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
        f"Reply in {lang_name} - this is the language the user has chosen for the whole session, "
        "regardless of what language the CONTEXT above happens to be written in. Never switch "
        "language to match the CONTEXT's language.\n\n"
        "Keep answers concise and friendly."
    )
    user = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
    return strip_decorative_symbols(_complete(system, user))


def answer_with_context(question: str, context_chunks: list[str], language: str) -> str:
    # Disk-cached (same shared, persistent cache as summarize()/
    # generate_suggested_questions() below) rather than the old in-memory
    # @lru_cache: this is the endpoint that fires on every single chat
    # message/voice message, so it's the single biggest source of Groq
    # calls in the whole app - keeping it in-memory-only meant every
    # restart/redeploy silently threw the whole cache away and started
    # re-paying for identical FAQ-style questions from scratch, and a
    # second worker process (if you ever run more than one) never saw
    # what the first had already answered. Keyed on the exact question +
    # exact retrieved context chunks + language, same as before - only the
    # identical question against the identical context is ever reused, so
    # this never mixes up answers across different pages/courses.
    key_parts = (question, tuple(context_chunks), language)
    return _disk_cached("answer", key_parts, lambda: _cached_answer_impl(question, tuple(context_chunks), language))


def _word_count_of(text: str) -> int:
    return len(text.split())


def summarize(text: str, length: str, language: str, title: str | None = None,
              word_count: int | None = None) -> str:
    """Disk-cached wrapper: the same course/module (identified by its exact
    text) + length/language/title/word_count only ever hits Groq once,
    persisted across restarts - see the disk-cache block near the top of
    this file. If the underlying course text is later edited, that's a
    different `text` value, so it's a cache miss and gets summarized fresh
    automatically; the old entry just sits unused."""
    key_parts = (text, length, language, title, word_count)
    return _disk_cached("summarize", key_parts, lambda: _summarize_impl(text, length, language, title, word_count))


def _summarize_impl(text: str, length: str, language: str, title: str | None,
                     word_count: int | None) -> str:
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
        f"overly brief - use the full word range you're given below. Reply in {lang_name} - this "
        "is the language the user chose for this session, regardless of what language the CONTENT "
        "below is written in. Never switch language to match the CONTENT's language."
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
    # range spelled out. Capped to ONE retry (not two) - each retry resends
    # the full content plus a correction note, so every extra retry is
    # close to another full summarize call's worth of tokens; one retry
    # already fixes the vast majority of misses, and this only ever runs
    # once per unique summary now that summarize() is disk-cached above -
    # not worth 3x the tokens on every first-time summary for the last
    # few edge cases a second retry would catch.
    target_label = f"{word_count} words" if word_count else f"{low}-{high} words"
    for _ in range(1):
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

    return strip_decorative_symbols(summary)


_TRANSLATE_CHUNK_CHARS = 4500  # Google's free web-translate endpoint (via deep-translator) rejects requests over ~5000 chars - leave headroom
_TRANSLATE_MAX_RETRIES = 3  # the free endpoint occasionally 429s/errors under concurrent load; a few retries with backoff clears almost all of these

# The free translate.google.com endpoint isn't a real API - it's Google's
# web frontend, and it starts handing back HTTP-error pages (not 429s, an
# actual "Error 500 (Server Error)!!1500..." page, caught by
# _looks_like_translate_error_page below) once enough requests land on it
# in a short window. A wide worker pool sending a whole page's worth of
# text-node chunks at once is exactly that burst pattern. Capping
# concurrency + a bit of random jitter on the retry backoff spreads the
# same requests out over time instead of firing them all at once, which
# noticeably cuts the error-page rate under real page-translate load.
_TRANSLATE_MAX_WORKERS = 4


def translate(text: str, language: str) -> str:
    """Faithful translation (not a summary) - used for reading page/module
    text aloud in the requested language before it goes to TTS, and for
    individual "translate this page" DOM-node strings (see translate_batch
    below, which calls back into this same cached function per node). Goes
    through Google Translate (deep-translator, no API key) rather than an
    LLM - translation doesn't need reasoning, and this sidesteps Groq's
    rate limits and reasoning-token budget entirely. Long text is chunked
    internally (see _TRANSLATE_CHUNK_CHARS) so a full course/module reading
    isn't cut short by Google's per-request character cap - the whole
    page/module gets translated and read, not a partial excerpt.

    No cache decorator on THIS function itself - every path through it
    (the short-text return below, and each paragraph-chunk in the long-text
    split further down) bottoms out in _translate_chunk, which is already
    the server-side disk-backed cache. Caching here too would just be a
    second, redundant layer keyed the same way."""
    if language == "en" or not text.strip():
        return strip_decorative_symbols(text)
    if len(text) <= _TRANSLATE_CHUNK_CHARS:
        return _translate_chunk(text, language)

    # Split on paragraph boundaries (course text is tagged with "\n\n## "
    # headings by the widget) and pack them into chunks up to the char
    # limit, so each request stays under Google's cap while keeping
    # headings/paragraphs intact instead of cutting mid-sentence.
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for para in paragraphs:
        para_chars = len(para)
        if current and current_chars + para_chars > _TRANSLATE_CHUNK_CHARS:
            chunks.append("\n\n".join(current))
            current, current_chars = [], 0
        current.append(para)
        current_chars += para_chars
    if current:
        chunks.append("\n\n".join(current))

    # Chunks are independent HTTP calls with no shared state, so they're
    # dispatched in parallel instead of one-at-a-time - for a long
    # module/page this is the single biggest speed win available here
    # (N chunks in ~1 chunk's latency instead of N chunks' worth).
    with ThreadPoolExecutor(max_workers=min(_TRANSLATE_MAX_WORKERS, len(chunks))) as pool:
        translated_chunks = list(pool.map(lambda c: _translate_chunk(c, language), chunks))
    return "\n\n".join(translated_chunks)


# Signatures of Google's own HTTP-error HTML page (500/503/etc). Under load
# (e.g. this batch's parallel requests, or Google's own free-endpoint
# throttling) translate.google.com can return one of these error pages
# instead of a translation - and deep-translator doesn't always recognize
# that as a failure, since the page still parses as *some* text at the DOM
# position it scrapes. Left unchecked, that error-page text gets accepted
# as a "successful" translation and shown to the user (e.g. "Error 500
# (Server Error)!!1500...") instead of the real content. Checked as a
# substring match (case-insensitive) so it still catches the page regardless
# of exact wording/formatting.
_TRANSLATE_ERROR_SIGNATURES = ("error 500", "error 503", "server error", "that's all we know")


def _looks_like_translate_error_page(s: str) -> bool:
    lowered = s.lower()
    return any(sig in lowered for sig in _TRANSLATE_ERROR_SIGNATURES)


def _backoff_with_jitter(delay: float) -> float:
    # Plain exponential backoff means every concurrently-throttled worker in
    # the pool wakes up and retries at the SAME moment, which just recreates
    # the same burst that got them throttled in the first place. Adding
    # +/-30% random jitter spreads those retries out over time instead.
    return delay * random.uniform(0.7, 1.3)


def _translate_chunk(text: str, language: str) -> str:
    """Server-side cached wrapper - see the disk-cache block near the top
    of this file. The exact same source text + target language only ever
    hits Google Translate once, persisted across restarts and shared by
    every visitor who requests that language, not just repeat visits from
    the same browser.

    Deliberately does NOT just call _disk_cached directly: _translate_chunk
    _impl fails open (returns the original, untranslated text) when Google
    Translate errors out after retries - see its tail end below. If that
    fail-open result got cached like a normal success, a transient hiccup
    (one rate-limited/erroring request) would permanently poison the cache
    for that exact text+language: every later visitor would be served the
    untranslated original forever, with no future retry ever able to fix
    it, since it'd be a cache HIT from then on. So: check the cache first
    same as _disk_cached would, but on a miss call the impl directly and
    only persist the result when it actually came from Google Translate -
    a fail-open result is returned as-is without ever entering the cache,
    so the NEXT request for that same text+language gets a fresh attempt."""
    key = _response_cache_key("translate_chunk", text, language)
    with _RESPONSE_CACHE_LOCK:
        cache = _load_response_cache()
        if key in cache:
            return cache[key]
    translated, ok = _translate_chunk_impl(text, language)
    if ok:
        with _RESPONSE_CACHE_LOCK:
            _stage_response_cache_write(key, translated)
    return translated


def _translate_chunk_impl(text: str, language: str) -> tuple[str, bool]:
    """Returns (translated_text, ok) - ok is False on the fail-open path
    (original text returned untranslated after retries are exhausted), so
    the caller above knows not to cache it."""
    target = _DT_LANG.get(language, "en")
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(_TRANSLATE_MAX_RETRIES + 1):
        try:
            translated = GoogleTranslator(source="auto", target=target).translate(text)
            if translated and _looks_like_translate_error_page(translated):
                # Not a real translation - Google's backend served an error
                # page and the library didn't raise for it. Treat exactly
                # like TooManyRequests: retry with backoff, then fail open.
                last_exc = RuntimeError("Google Translate returned an error-page response, not a translation")
                if attempt < _TRANSLATE_MAX_RETRIES:
                    sleep_for = _backoff_with_jitter(delay)
                    logger.warning("Google Translate returned an error page, retrying in %.1fs (attempt %d/%d).",
                                    sleep_for, attempt + 1, _TRANSLATE_MAX_RETRIES)
                    time.sleep(sleep_for)
                    delay *= 2
                    continue
                break
            return strip_decorative_symbols(translated or text), True
        except TooManyRequests as exc:
            last_exc = exc
            if attempt < _TRANSLATE_MAX_RETRIES:
                sleep_for = _backoff_with_jitter(delay)
                logger.warning("Google Translate rate limited, retrying in %.1fs (attempt %d/%d).",
                                sleep_for, attempt + 1, _TRANSLATE_MAX_RETRIES)
                time.sleep(sleep_for)
                delay *= 2
        except (RequestError, TranslationNotFound) as exc:
            last_exc = exc
            break
        except Exception as exc:  # noqa: BLE001 - network hiccups (DNS, connection
            # reset, timeout) surface as requests' own exception types, not
            # deep_translator's; treat them the same as the named cases above -
            # fail open to the original text rather than raising out of a
            # thread-pool worker and taking down the whole batch/request.
            last_exc = exc
            break
    # Fail open: never block the page/read-aloud on a translation hiccup -
    # surface the original text rather than raising, and let the caller's
    # logs show why (translate_batch/translate.py's router log this too).
    logger.warning("Google Translate failed for a %d-char chunk (%s); returning source text untranslated.",
                    len(text), last_exc)
    return strip_decorative_symbols(text), False


_TRANSLATE_PACK_MAX_ITEMS = 40  # cap so one bad merge only costs a retry on 40 items, not the whole page
# Separator used to merge several short DOM-node strings into ONE Google
# Translate call. Chosen so it survives both ends of the pipeline: it's a
# single newline (not the 3+ run that strip_decorative_symbols collapses),
# wrapped around U+2063 INVISIBLE SEPARATOR - a character with no visible
# glyph, no translatable meaning, and no plausible reason for Google
# Translate to reorder, merge, or "helpfully" rephrase around it the way it
# sometimes does with visible punctuation.
_TRANSLATE_PACK_SEP = "\n\u2063\n"


def translate_batch(texts: tuple[str, ...], language: str) -> list[str]:
    """Translates a list of independent text-node strings - each one exactly
    what gets swapped back into ONE DOM node in place (a heading, a button
    label, a paragraph, a link) - for the "translate this page" feature.
    Must return a list the same length, in the same order, as `texts`, since
    the caller maps result[i] straight onto the DOM node that produced
    texts[i].

    A course-content page walk can easily produce a couple hundred of these
    strings. The old version of this function gave each one its own Google
    Translate HTTP call (capped at 4 concurrent) - correct, but for a page
    with a couple hundred first-time (uncached) nodes that's dozens of
    sequential rounds of network latency, which is most of why a first
    translate of a content-heavy page could take tens of seconds. This
    version still checks the disk cache per item (so a single edited node
    never invalidates its neighbors, and a fully-warm page is still a plain
    dict read with zero network calls) but, for whatever's actually a cache
    MISS, packs many short items into ONE Google Translate call each instead
    of one call per item - see _TRANSLATE_PACK_SEP above and run_pack below
    for how each pack's result is split back apart and verified before it's
    trusted."""
    if not texts:
        return []
    if language == "en":
        return [strip_decorative_symbols(t) for t in texts]

    # Items that are blank (or already have no translatable letters, e.g.
    # "$99", "->") don't need a network call at all - skip them here.
    indices_to_translate = [i for i, t in enumerate(texts) if t and t.strip()]
    results: list[str] = list(texts)
    if not indices_to_translate:
        return results

    # Cache lookups stay PER ITEM (unchanged from before) - this is what
    # keeps a warm page instant and keeps one changed sentence from
    # invalidating anything else's cached translation.
    keys = {i: _response_cache_key("translate_chunk", texts[i], language) for i in indices_to_translate}
    misses: list[int] = []
    with _RESPONSE_CACHE_LOCK:
        cache = _load_response_cache()
        for i in indices_to_translate:
            key = keys[i]
            if key in cache:
                results[i] = cache[key]
            else:
                misses.append(i)
    if not misses:
        return results

    # Only misses ever touch the network. Pack them into groups that fit
    # Google's free-endpoint char cap (same _TRANSLATE_CHUNK_CHARS budget
    # used for chunking one long text), leaving room for the separators.
    packs: list[list[int]] = []
    current: list[int] = []
    current_chars = 0
    for i in misses:
        item_chars = len(texts[i]) + len(_TRANSLATE_PACK_SEP)
        if current and (len(current) >= _TRANSLATE_PACK_MAX_ITEMS
                        or current_chars + item_chars > _TRANSLATE_CHUNK_CHARS):
            packs.append(current)
            current, current_chars = [], 0
        current.append(i)
        current_chars += item_chars
    if current:
        packs.append(current)

    def run_pack(pack: list[int]) -> None:
        if len(pack) == 1:
            i = pack[0]
            results[i] = _translate_chunk(texts[i], language)
            return

        joined = _TRANSLATE_PACK_SEP.join(texts[i] for i in pack)
        translated_joined, ok = _translate_chunk_impl(joined, language)
        parts = translated_joined.split(_TRANSLATE_PACK_SEP.strip("\n")) if ok else []

        if ok and len(parts) == len(pack):
            # Clean split, right count - trust it, and cache each piece
            # under its OWN item key so future single-node lookups (and
            # future packs that happen to include this item alongside
            # different neighbors) still hit the cache individually.
            for i, part in zip(pack, parts):
                translated = strip_decorative_symbols(part)
                results[i] = translated
                with _RESPONSE_CACHE_LOCK:
                    _stage_response_cache_write(keys[i], translated)
            return

        # Merge didn't come back clean (Google dropped/reformatted the
        # separator, or the request failed outright) - fall back to the
        # old one-call-per-item path for just this pack rather than
        # guessing which returned piece belongs to which DOM node.
        # Correctness always wins over the speedup.
        for i in pack:
            results[i] = _translate_chunk(texts[i], language)

    with ThreadPoolExecutor(max_workers=_TRANSLATE_MAX_WORKERS) as pool:
        list(pool.map(run_pack, packs))

    return results



def generate_suggested_questions(context_text: str, language: str, count: int = 5) -> list[dict]:
    """Disk-cached wrapper - see summarize() above for why. Same
    context_text + language + count only ever hits Groq once, persisted
    across restarts, and stays correct automatically if context_text
    changes (different key -> regenerated fresh)."""
    key_parts = (context_text, language, count)
    return _disk_cached("suggested_questions", key_parts,
                         lambda: _generate_suggested_questions_impl(context_text, language, count))


def _generate_suggested_questions_impl(context_text: str, language: str, count: int) -> list[dict]:
    lang_name = _LANG_NAME.get(language, "English")
    system = (
        "You are the Rozzgaar website assistant. Based on the given content, propose sample "
        "questions a prospective student might ask, with short accurate answers grounded only "
        f"in the content. Reply in {lang_name} - this is the language the user chose for this "
        "session, regardless of what language the CONTENT below is written in. Never switch "
        "language to match the CONTENT's language. Do not use emoji or decorative symbols/icons "
        "anywhere in the question or answer text - these are read aloud by text-to-speech. "
        "Respond with ONLY a JSON array, no markdown, no commentary, in this exact shape: "
        '[{"question": "...", "answer": "..."}]'
    )
    user = f"CONTENT:\n{context_text}\n\nGenerate exactly {count} question/answer pairs."
    raw = _complete(system, user, temperature=0.4, max_tokens=800)
    qa = _safe_parse_qa(raw)
    return [
        {"question": strip_decorative_symbols(item["question"]), "answer": strip_decorative_symbols(item["answer"])}
        for item in qa
    ]


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