/**
 * page-intents.js
 * -----------------------------------------------------------------------
 * Drop this into your site (or merge into test-widget.html) alongside the
 * existing chat widget script. It adds three things:
 *
 *   1. extractModuleText(userMessage)  — pulls the right chunk of the DOM
 *      when the user says "summarize module 1", "explain module 2", etc.
 *      Falls back to the whole visible page text otherwise.
 *
 *   2. handleSummarizeIntent(userMessage, language) — calls your existing
 *      POST /summarize/ endpoint with raw `text` (no backend change needed).
 *
 *   3. handleReadModuleIntent(courseSlug, userMessage, language) — calls the
 *      REAL /modules/read endpoint (app/routers/module_read.py in this
 *      package, built against your actual content_fetcher.py/llm.py/tts.py)
 *      which fetches the module fresh from the Rozzgaar API, translates if
 *      needed, and returns spoken audio.
 *
 * CONFIRMED from your real site (rozzgaar.in/applicant/course-content):
 *   - Course slug is a URL query param: ?slug=edp  -> trivial to read, no
 *     DOM guessing needed.
 *   - The viewer shows ONE chapter at a time; its title is
 *     <div class="viewer-title">Chapter N: ...</div>. There is no need to
 *     search across multiple module headings on the page - "summarize this
 *     module" / "read this module" always means "whatever's currently open
 *     in the viewer".
 *
 * STILL A GUESS (only remaining placeholder):
 *   - The container that wraps the chapter BODY text alongside
 *     .viewer-title. I only have the title element confirmed, not its
 *     parent/sibling structure, so extractCurrentModuleText() below walks
 *     up from .viewer-title looking for an ancestor with enough visible
 *     text. If it grabs too much (e.g. sidebar nav bleeding in) or too
 *     little, send me one more Inspect snippet: the .viewer-title element's
 *     PARENT (one level up) with Copy Element, and I'll replace the walk-up
 *     heuristic with an exact selector.
 * -----------------------------------------------------------------------
 */

const API_BASE = "http://127.0.0.1:8001"; // TODO: change to your deployed API URL

const MODULE_TITLE_SELECTOR = ".viewer-title"; // confirmed real class from your site

/** Reads the course slug straight from the URL, e.g. ?slug=edp -> "edp" */
function getCourseSlugFromPage() {
  return new URLSearchParams(window.location.search).get("slug");
}

/**
 * The viewer only ever shows one chapter at a time, so there's no module
 * number to search for - just grab whatever's currently displayed.
 * Walks up from .viewer-title until it finds an ancestor with enough
 * visible text to plausibly include the chapter body (not just the title).
 */
function extractCurrentModuleText() {
  const titleEl = document.querySelector(MODULE_TITLE_SELECTOR);
  if (!titleEl) return document.body.innerText; // fallback: whole page

  let container = titleEl.parentElement;
  for (let i = 0; i < 4 && container; i++) {
    const len = (container.innerText || "").trim().length;
    if (len > 200) break; // looks like it includes real body content now
    container = container.parentElement;
  }
  return (container || titleEl).innerText.trim();
}

/** Kept for backwards compatibility with tryHandlePageIntent() below. */
function extractModuleText(_userMessage) {
  return extractCurrentModuleText();
}

/** Very small intent check — expand as needed. */
function isReadModuleIntent(userMessage) {
  return /read\s+(this\s+)?module/i.test(userMessage) ||
         /module\s*\d+.*(read|listen|bol|sunao)/i.test(userMessage);
}

function isSummarizeIntent(userMessage) {
  return /summar(y|ize|ise)/i.test(userMessage) ||
         /is page ko (summarize|summary)/i.test(userMessage);
}

/** Calls the EXISTING /summarize/ endpoint with page/module text. No backend change needed. */
async function handleSummarizeIntent(userMessage, language = "auto") {
  const text = extractModuleText(userMessage);
  const res = await fetch(`${API_BASE}/summarize/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, length: "short", language }),
  });
  if (!res.ok) throw new Error(`Summarize failed: ${res.status}`);
  return res.json(); // { summary, language, ... } — matches your existing /summarize/ response shape
}

/**
 * Calls the /modules/read endpoint (fresh from API, spoken back).
 * Since the viewer only shows one chapter at a time, the most reliable
 * "which module?" signal is the on-screen .viewer-title text itself -
 * e.g. "Chapter 1: Building the Founder's Mindset..." - not the user's
 * phrasing. Falls back to the user's message only if no title is found.
 */
async function handleReadModuleIntent(userMessage, language = "auto") {
  const courseSlug = getCourseSlugFromPage();
  if (!courseSlug) throw new Error("Could not determine course slug for this page.");

  const titleEl = document.querySelector(MODULE_TITLE_SELECTOR);
  const moduleQuery = titleEl ? titleEl.textContent.trim() : userMessage;

  const res = await fetch(`${API_BASE}/modules/read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      course_slug: courseSlug,
      module_query: moduleQuery,
      language,
    }),
  });
  if (!res.ok) throw new Error(`Read-module failed: ${res.status}`);
  const data = await res.json();
  // Speak the returned transcript via the browser's native Web Speech API
  // instead of playing server-generated audio - no data: URI, so no page
  // CSP media-src restrictions to worry about, and no server-TTS reliance.
  if (data.transcript && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(data.transcript);
    if (language && language !== "auto") utterance.lang = language;
    window.speechSynthesis.speak(utterance);
  }
  return data; // { module_title, transcript, audio_base64, audio_mime }
}

/**
 * Router you can call from your existing chat "submit" handler BEFORE
 * falling back to the normal /chat/ call — put this check first.
 */
async function tryHandlePageIntent(userMessage, language = "auto") {
  if (isReadModuleIntent(userMessage)) {
    return { type: "read_module", result: await handleReadModuleIntent(userMessage, language) };
  }
  if (isSummarizeIntent(userMessage)) {
    return { type: "summarize", result: await handleSummarizeIntent(userMessage, language) };
  }
  return null; // not a page intent — fall through to normal /chat/
}