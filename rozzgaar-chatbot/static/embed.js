/**
 * embed.js - Rozzgaar Assistant widget
 * -----------------------------------------------------------------------
 * Drop this ONE script tag into course-content.php (near the end of
 * <body>, after the page's own inline <script> block). Because
 * course-content.php is already slug-agnostic (course is picked from
 * ?slug=... at runtime), adding it there once makes the widget appear
 * on every course page automatically - no per-course wiring needed.
 *
 *   <script defer src="https://tropical-refocus-exact.ngrok-free.dev/static/embed.js"></script>
 *
 * What it does:
 *   1. Injects the chat bubble UI once the DOM is ready (never touches
 *      document.body before it exists).
 *   2. Extracts the visible page/module text so the bot has real context
 *      (mirrors static/test-widget.html's extractPageContent()).
 *   3. Routes "summarize this" / "read this module" through the
 *      /summarize/ and /modules/read endpoints (page-intent.js logic)
 *      BEFORE falling back to the general /chat/ endpoint.
 *   4. Supports voice input (/voice/chat) and click-to-hear TTS
 *      (/tts/speak), same as the test widget.
 * -----------------------------------------------------------------------
 */
(function () {
  "use strict";

  // Guard against double-inclusion (e.g. script tag pasted twice).
  if (window.__rzgWidgetLoaded) return;
  window.__rzgWidgetLoaded = true;

  // ------------------------------------------------------------------
  // CONFIG - only line you should need to touch when the tunnel changes.
  // ------------------------------------------------------------------
  const CONFIG = {
    BACKEND_URL: "https://tropical-refocus-exact.ngrok-free.dev",
  };

  // Smiling robot icon matching the reference image the user provided:
  // thin white outline, rounded-square head, antenna, single ear tick on
  // each side, two dot eyes, and a smile curve. `size` in px.
  //
  // Every shape - antenna tip, ear ticks, head outline, eyes, mouth -
  // sits comfortably inside a margin from the 0-24 viewBox edges
  // (antenna top stops at y=1.95, ear ticks stop at x=2.9/x=21.1), so
  // nothing clips or pokes out of the circular launcher button at any
  // size - this was the original "edge" clipping problem.
  function assistantIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <line x1="12" y1="2.6" x2="12" y2="5.4" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>
        <rect x="5.2" y="6.6" width="13.6" height="10.8" rx="3.4" fill="none" stroke="#fff" stroke-width="1.3"/>
        <line x1="2.9" y1="10.6" x2="5.2" y2="10.6" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>
        <line x1="18.8" y1="10.6" x2="21.1" y2="10.6" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>
        <circle cx="9.3" cy="11.3" r="1" fill="#fff"/>
        <circle cx="14.7" cy="11.3" r="1" fill="#fff"/>
        <path d="M9.3 14.6 Q12 16.6 14.7 14.6" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>
      </svg>`;
  }

  // Sophisticated line-art icons for the quick-action buttons (replaces
  // the plain emoji glyphs with icons that match assistantIconSvg's style).
  function readIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 6c-1.7-1.1-3.9-1.5-6-1.2-.9.1-1.5.3-1.5.3v13.4s.7-.2 1.6-.3c2-.3 4.1.1 5.9 1.2M12 6c1.7-1.1 3.9-1.5 6-1.2.9.1 1.5.3 1.5.3v13.4s-.7-.2-1.6-.3c-2-.3-4.1.1-5.9 1.2M12 6v13.4"
              stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`;
  }
  function summaryIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="4.5" y="3.25" width="15" height="17.5" rx="2.2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M7.8 8h8.4M7.8 11.6h8.4M7.8 15.2h5.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>`;
  }
  function sampleQIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4.5 5.8c0-1.2 1-2.2 2.2-2.2h10.6c1.2 0 2.2 1 2.2 2.2v8.6c0 1.2-1 2.2-2.2 2.2H9.4L6 19.9v-3.3h-.3c-1.2 0-2.2-1-2.2-2.2V5.8Z"
              stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M9.7 9.2c0-1.25 1.05-2.2 2.3-2.2 1.25 0 2.3.95 2.3 2.1 0 1.55-2.05 1.55-2.3 3"
              stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="12" cy="14.6" r="1" fill="currentColor"/>
      </svg>`;
  }
  // Sophisticated line-art microphone icon (replaces the plain emoji).
  // Two states are drawn: idle (outline) and recording (filled), toggled
  // via the rzg-mic-recording class in injectStyles() below.
  function micIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="9" y="2.5" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.6"/>
        <path d="M5.5 11.2v1a6.5 6.5 0 0 0 13 0v-1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        <path d="M12 18.2v3M9 21.2h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
      </svg>`;
  }
  // Sophisticated line-art speaker/volume icon (replaces the plain 🔊
  // emoji on the sample-question chips - emoji rendering varies across
  // devices/OS fonts, this stays consistent and matches the other
  // stroke-based icons above).
  function speakerIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4.5 9.5v5h3l4.5 3.6V5.9L7.5 9.5h-3Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M16 9a4 4 0 0 1 0 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M18.6 6.8a7.5 7.5 0 0 1 0 10.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>`;
  }

  // Injects WhatsApp-style chat bubble CSS once per page: green tailed
  // bubbles for the user (right), white tailed bubbles for the bot
  // (left), and small timestamp text - matching WhatsApp's actual look.
  function injectChatStyles() {
    if (document.getElementById("rzg-chat-styles")) return;
    const style = document.createElement("style");
    style.id = "rzg-chat-styles";
    style.textContent = `
      #rzg-log {
        background-color: #ECE5DD;
      }
      .rzg-bubble-row { display: flex; margin: 1px 0; }
      .rzg-bubble {
        position: relative;
        max-width: 78%;
        padding: 6px 8px 8px 9px;
        font-size: 13.5px;
        line-height: 1.35;
        box-shadow: 0 1px 0.5px rgba(0,0,0,.13);
        word-wrap: break-word;
        white-space: pre-wrap;
      }
      .rzg-bubble-user {
        margin-left: auto;
        background: #FDE9DE;
        border-radius: 8px;
        color: #111;
      }
      .rzg-bubble-bot {
        margin-right: auto;
        background: #fff;
        border-radius: 8px;
        color: #111;
        cursor: pointer;
      }
      .rzg-bubble-time {
        display: block;
        text-align: right;
        font-size: 10.5px;
        color: rgba(0,0,0,.45);
        margin-top: 2px;
        margin-left: 8px;
        float: right;
      }
    `;
    document.head.appendChild(style);
  }


  // Injects the pulsing "listening" animation once per page. Applied to
  // #rzg-micBtn via the .rzg-mic-recording class while recording is active.
  function injectMicStyles() {
    if (document.getElementById("rzg-mic-styles")) return;
    const style = document.createElement("style");
    style.id = "rzg-mic-styles";
    style.textContent = `
      @keyframes rzg-pulse-ring {
        0%   { transform: scale(0.85); opacity: 0.55; }
        70%  { transform: scale(1.9);  opacity: 0; }
        100% { transform: scale(1.9);  opacity: 0; }
      }
      @keyframes rzg-mic-bounce {
        0%, 100% { transform: scale(1); }
        50%      { transform: scale(1.1); }
      }
      #rzg-micBtn { position: relative; transition: background .15s, color .15s, border-color .15s; }
      #rzg-micBtn.rzg-mic-recording {
        background: #E8734A !important;
        color: #fff !important;
        border-color: #E8734A !important;
        animation: rzg-mic-bounce 1s ease-in-out infinite;
      }
      #rzg-micBtn.rzg-mic-recording::before,
      #rzg-micBtn.rzg-mic-recording::after {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 2px solid #E8734A;
        animation: rzg-pulse-ring 1.6s ease-out infinite;
        pointer-events: none;
      }
      #rzg-micBtn.rzg-mic-recording::after { animation-delay: .55s; }
    `;
    document.head.appendChild(style);
  }

  // ------------------------------------------------------------------
  // Bilingual UI copy for the widget chrome itself (button labels, status
  // messages, the language-gate). This is separate from the *content*
  // language (page text / LLM replies), which the backend already handles
  // via the `language` field on every request - this table just keeps the
  // widget's own labels in sync with whichever language the user picked.
  // ------------------------------------------------------------------
  const UI_TEXT = {
    hi: {
      chooseLangTitle: "भाषा चुनें",
      chooseLangSub: "कृपया अपनी पसंदीदा भाषा चुनें",
      langHiLabel: "हिंदी",
      langEnLabel: "English",
      welcome: "मैं यहाँ आपकी मदद के लिए हूँ - इस पेज की सामग्री पढ़ने, उसका सारांश देने, या सवाल सुझाने में।",
      readLabel: "पढ़ें", readBusy: "...", readTitle: "इस पेज को ज़ोर से सुनें",
      summaryLabel: "सारांश", summaryBusy: "...", summaryTitle: "इस पेज का सारांश सुनें",
      sampleLabel: "नमूना सवाल", sampleBusy: "...", sampleTitle: "नमूना सवाल-जवाब सुनें",
      readingNow: "🔊 पेज पढ़ा जा रहा है...",
      nothingToRead: "इस पेज पर पढ़ने के लिए कुछ नहीं मिला।",
      notEnoughForSummary: "सारांश बनाने के लिए इस पेज पर पर्याप्त सामग्री नहीं है।",
      summaryPreparing: "सारांश तैयार हो रहा है...",
      summaryFailed: "अभी सारांश नहीं बन पाया। कृपया दोबारा कोशिश करें।",
      notEnoughForSample: "सवाल बनाने के लिए इस पेज पर पर्याप्त सामग्री नहीं है।",
      samplePreparing: "नमूना सवाल तैयार हो रहे हैं...",
      sampleReady: "यहाँ कुछ नमूना सवाल हैं - दोबारा सुनने के लिए किसी पर टैप करें:",
      sampleFailed: "अभी सवाल नहीं बन पाए। कृपया दोबारा कोशिश करें।",
      sampleChipLabel: "सवाल",
      sampleNone: "इस पेज के लिए कोई सवाल नहीं बन पाए।",
      clickToHear: "सुनने के लिए यहाँ दोबारा क्लिक करें",
      placeholder: "इस पेज के बारे में पूछें...",
      unreachable: "अभी सहायक तक नहीं पहुँच पा रहे - कृपया थोड़ी देर में कोशिश करें।",
      closingReply: "आपके समय के लिए धन्यवाद! जब चाहें, फिर से जुड़ें। 👋",
      micNoInput: "मुझे कुछ सुनाई नहीं दिया - माइक बटन दबाकर दोबारा कोशिश करें।",
    },
    en: {
      chooseLangTitle: "Choose language",
      chooseLangSub: "Please select your preferred language",
      langHiLabel: "हिंदी",
      langEnLabel: "English",
      welcome: "I am here to help you with the content - read it, summarize it, or suggest questions in your selected language.",
      readLabel: "Read", readBusy: "...", readTitle: "Listen to this page read aloud",
      summaryLabel: "Summary", summaryBusy: "...", summaryTitle: "Listen to a summary of this page",
      sampleLabel: "Sample Q&A", sampleBusy: "...", sampleTitle: "Listen to sample questions and answers",
      readingNow: "🔊 Reading the page...",
      nothingToRead: "There's nothing on this page to read yet.",
      notEnoughForSummary: "There isn't enough content on this page to summarize.",
      summaryPreparing: "Preparing the summary...",
      summaryFailed: "Could not prepare a summary right now. Please try again.",
      notEnoughForSample: "There isn't enough content on this page to build questions.",
      samplePreparing: "Preparing sample questions...",
      sampleReady: "Here are some sample questions - tap any one to hear it again:",
      sampleFailed: "Could not prepare questions right now. Please try again.",
      sampleChipLabel: "Question",
      sampleNone: "No questions could be generated for this page.",
      clickToHear: "Click here to hear this again",
      placeholder: "Ask about this page...",
      unreachable: "Could not reach the assistant right now - please try again in a moment.",
      closingReply: "Thank you for your time. Feel free to connect anytime! 👋",
      micNoInput: "I didn't hear anything - tap the mic button to try again.",
    },
  };

  // Phrases (English + common Hindi/Hinglish variants) that mean "end the
  // conversation" rather than a real question - checked against the raw
  // transcript/typed text BEFORE it's sent to the backend, so "stop",
  // "close this", "band karo" etc. close the widget instead of being
  // treated as a chat message. Matches on trimmed, lowercased, punctuation
  // -stripped text so short exact-ish phrases don't false-positive on
  // longer real questions (e.g. "how do I stop the video" is NOT closed
  // because it isn't an exact/near-exact match to a close phrase).
  const CLOSE_COMMANDS = [
    "close", "stop", "close this", "close it", "close chat", "close the chat",
    "stop it", "bye", "bye bye", "goodbye", "good bye", "exit", "quit",
    "end chat", "end the chat", "thats all", "that's all", "thanks bye",
    "band karo", "bandh karo", "band kar do", "bandh kar do", "band kardo",
    "bandh kardo", "close kar do", "close karo", "chat band karo",
    "band karna", "ruk jao", "bas", "bas karo", "bye chatbot",
  ];

  function isCloseCommand(rawText) {
    const text = (rawText || "")
      .toLowerCase()
      .trim()
      .replace(/[.!?,]+$/g, "");
    if (!text) return false;
    return CLOSE_COMMANDS.includes(text);
  }

  // ------------------------------------------------------------------
  // Page-content extraction (adapted for the real course-content.php
  // markup: .course-viewer holds the active chapter, .dash-content is
  // the fallback for every other dashboard page).
  // ------------------------------------------------------------------
  const CONTENT_NOISE_SELECTOR = [
    "script", "style", "noscript", "svg", "iframe",
    "nav", "footer", "header",
    "[aria-hidden='true']", "[hidden]",
    ".viewer-watermark", ".course-toc", ".learn-mobile-bar", ".dash-sidebar",
    "#rzg-chat-widget", "#rzg-extract-debug",
  ].join(",");

  const MAIN_CONTENT_SELECTORS = [
    ".course-viewer", ".dash-content",
    "main", "[role='main']", "article",
    "#content", ".content", "#app", "#root",
  ];

  const MIN_USEFUL_CONTENT_CHARS = 40;
  const MAX_SENT_CONTENT_CHARS = 20000;
  const MODULE_TITLE_SELECTOR = ".viewer-title";

  function cleanElementText(el) {
    const clone = el.cloneNode(true);
    clone.querySelectorAll(CONTENT_NOISE_SELECTOR).forEach((n) => n.remove());

    // Tag every heading with a "## " marker before flattening to text, so
    // the backend can split the page into named sections and read back
    // just the one the user asked for (e.g. "read the Eligibility
    // Criteria heading") instead of the entire page every time.
    clone.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((h) => {
      const heading = (h.textContent || "").trim();
      if (heading) h.textContent = `\n\n## ${heading}\n`;
    });

    const text = (clone.innerText || clone.textContent || "")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    return text.slice(0, MAX_SENT_CONTENT_CHARS);
  }

  function extractPageContent() {
    let root = document.body;
    for (const selector of MAIN_CONTENT_SELECTORS) {
      const el = document.querySelector(selector);
      if (el && (el.innerText || "").trim().length > MIN_USEFUL_CONTENT_CHARS) {
        root = el;
        break;
      }
    }
    return cleanElementText(root);
  }

  function getCourseSlugFromPage() {
    return new URLSearchParams(window.location.search).get("slug");
  }

  /** Course content only: prefers the dedicated .course-viewer wrapper
   *  (cleaned of the sidebar/TOC/watermark/nav via CONTENT_NOISE_SELECTOR)
   *  so Read/Summarize/Sample Questions speak just the lesson text, not
   *  surrounding dashboard chrome. Falls back to walking up from the
   *  chapter title, then to the general page extractor, if .course-viewer
   *  isn't present on this page. */
  function extractCurrentModuleText() {
    const courseEl = document.querySelector(".course-viewer");
    if (courseEl && (courseEl.innerText || "").trim().length > MIN_USEFUL_CONTENT_CHARS) {
      return cleanElementText(courseEl);
    }

    const titleEl = document.querySelector(MODULE_TITLE_SELECTOR);
    if (!titleEl) return extractPageContent();
    let container = titleEl.parentElement;
    for (let i = 0; i < 4 && container; i++) {
      if ((container.innerText || "").trim().length > 200) break;
      container = container.parentElement;
    }
    return cleanElementText(container || titleEl);
  }

  // ------------------------------------------------------------------
  // Speech playback via the browser's native Web Speech API. There's no
  // <audio src>, blob:, or data: URI involved at all - speechSynthesis
  // renders audio locally - so page CSP media-src restrictions never
  // come into play, and it sidesteps server-side TTS (edge-tts/gTTS)
  // reliability entirely. Module-scope so both initWidget() and
  // handleReadModuleIntent() can call it.
  // ------------------------------------------------------------------
  function speakText(text, language) {
    if (!text || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel(); // stop anything already speaking
    const utterance = new SpeechSynthesisUtterance(text);
    if (language && language !== "auto") utterance.lang = language;
    window.speechSynthesis.speak(utterance);
  }

  /** Speaks several pieces of text back-to-back (e.g. question then answer,
   *  repeated for each sample Q&A) without cutting earlier ones off - calls
   *  to speechSynthesis.speak() queue automatically as long as cancel()
   *  isn't called in between. */
  function speakQueue(texts, language) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    (texts || []).forEach((t) => {
      if (!t) return;
      const utterance = new SpeechSynthesisUtterance(t);
      if (language && language !== "auto") utterance.lang = language;
      window.speechSynthesis.speak(utterance);
    });
  }

  function isReadModuleIntent(msg) {
    return /read\s+(this\s+)?module/i.test(msg) ||
           /module\s*\d+.*(read|listen|bol|sunao)/i.test(msg);
  }
  function isSummarizeIntent(msg) {
    return /summar(y|ize|ise)/i.test(msg) ||
           /is page ko (summarize|summary)/i.test(msg);
  }

  async function handleSummarizeIntent(userMessage, language) {
    const text = extractCurrentModuleText();
    const res = await fetch(`${CONFIG.BACKEND_URL}/summarize/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, length: "short", language, message: userMessage }),
    });
    if (!res.ok) throw new Error(`Summarize failed: ${res.status}`);
    return res.json();
  }

  async function handleReadModuleIntent(userMessage, language) {
    const courseSlug = getCourseSlugFromPage();
    if (!courseSlug) throw new Error("Could not determine course slug for this page.");
    const titleEl = document.querySelector(MODULE_TITLE_SELECTOR);
    const moduleQuery = titleEl ? titleEl.textContent.trim() : userMessage;
    const res = await fetch(`${CONFIG.BACKEND_URL}/modules/read`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ course_slug: courseSlug, module_query: moduleQuery, language, message: userMessage }),
    });
    if (!res.ok) throw new Error(`Read-module failed: ${res.status}`);
    const data = await res.json();
    if (data.transcript) {
      speakText(data.transcript, language);
    }
    return data;
  }

  async function tryHandlePageIntent(userMessage, language) {
    if (isReadModuleIntent(userMessage)) {
      return { type: "read_module", result: await handleReadModuleIntent(userMessage, language) };
    }
    if (isSummarizeIntent(userMessage)) {
      return { type: "summarize", result: await handleSummarizeIntent(userMessage, language) };
    }
    return null;
  }

  // ------------------------------------------------------------------
  // Widget UI - built with createElement so nothing runs before the
  // DOM (and therefore document.body) actually exists.
  // ------------------------------------------------------------------
  function buildWidget() {
    // Floating launcher bubble - a robot icon, always visible when the
    // chat panel is closed. Tapping it opens the panel; the panel starts
    // hidden so the page isn't cluttered until the user asks for help.
    const launcher = document.createElement("button");
    launcher.id = "rzg-launcher";
    launcher.type = "button";
    launcher.title = "सहायक खोलें";
    launcher.setAttribute("aria-label", "सहायक खोलें");
    launcher.style.cssText = `
      position:fixed; bottom:16px; right:16px; width:58px; height:58px;
      z-index:9999; background:#E8734A; border:none; border-radius:50%;
      box-shadow:0 8px 20px rgba(0,0,0,0.28); cursor:pointer;
      display:flex; align-items:center; justify-content:center; color:#fff;
      line-height:1;`;
    launcher.innerHTML = assistantIconSvg(28);
    document.body.appendChild(launcher);

    const wrap = document.createElement("div");
    wrap.id = "rzg-chat-widget";
    wrap.style.cssText = `
      position:fixed; bottom:16px; right:16px; width:360px; max-width:calc(100vw - 32px);
      z-index:9999; background:#ECE5DD; border-radius:16px; overflow:hidden;
      box-shadow:0 12px 32px rgba(0,0,0,0.25); border:1px solid rgba(0,0,0,0.06);
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      display:none;`; // hidden until the launcher is clicked

    wrap.innerHTML = `
      <div style="background:#E8734A; color:#fff; padding:12px 14px; display:flex; align-items:center; gap:10px;" id="rzg-header">
        <div style="width:30px;height:30px;border-radius:50%;background:rgba(255,255,255,.25);display:flex;align-items:center;justify-content:center;color:#fff;">${assistantIconSvg(18)}</div>
        <div style="flex:1;"><div style="font-weight:600;font-size:14px;">Rozzgaar Assistant</div><div style="font-size:11px;opacity:.85;">Online</div></div>
        <button type="button" id="rzg-minimizeBtn" title="छोटा करें" aria-label="छोटा करें"
                style="background:rgba(255,255,255,.25); border:none; color:#fff; width:26px; height:26px; border-radius:50%; cursor:pointer; font-size:15px; line-height:1; flex-shrink:0;">−</button>
      </div>
      <div id="rzg-langGate" style="padding:22px 18px 24px; background:#ECE5DD; text-align:center;">
        <div style="font-weight:600; font-size:14.5px; color:#292524; margin-bottom:2px;">भाषा चुनें / Choose language</div>
        <div style="font-size:12px; color:#78716C; margin-bottom:16px;">कृपया अपनी पसंदीदा भाषा चुनें / Please select your preferred language</div>
        <div style="display:flex; gap:10px; justify-content:center;">
          <button type="button" id="rzg-langHi" style="flex:1; max-width:140px; background:#fff; border:1.5px solid #E8734A; color:#E8734A; border-radius:12px; padding:12px 8px; font-size:14px; font-weight:600; cursor:pointer; font-family:inherit;">हिंदी</button>
          <button type="button" id="rzg-langEn" style="flex:1; max-width:140px; background:#fff; border:1.5px solid #E8734A; color:#E8734A; border-radius:12px; padding:12px 8px; font-size:14px; font-weight:600; cursor:pointer; font-family:inherit;">English</button>
        </div>
      </div>
      <div id="rzg-quickActions" style="display:none; gap:6px; padding:10px 10px 0; background:#ECE5DD;">
        <button type="button" id="rzg-btnRead" title="Listen to this page read aloud"
                style="flex:1; display:flex; flex-direction:column; align-items:center; gap:3px; background:#fff; border:1px solid #E7E5E4; border-radius:10px; padding:9px 4px; cursor:pointer; font-family:inherit; color:#E8734A;">
          ${readIconSvg(19)}
          <span style="font-size:11.5px; font-weight:600; color:#44403C;">Read</span>
        </button>
        <button type="button" id="rzg-btnSummary" title="Listen to a summary of this page"
                style="flex:1; display:flex; flex-direction:column; align-items:center; gap:3px; background:#fff; border:1px solid #E7E5E4; border-radius:10px; padding:9px 4px; cursor:pointer; font-family:inherit; color:#E8734A;">
          ${summaryIconSvg(19)}
          <span style="font-size:11.5px; font-weight:600; color:#44403C;">Summary</span>
        </button>
        <button type="button" id="rzg-btnSample" title="Listen to sample questions and answers"
                style="flex:1; display:flex; flex-direction:column; align-items:center; gap:3px; background:#fff; border:1px solid #E7E5E4; border-radius:10px; padding:9px 4px; cursor:pointer; font-family:inherit; color:#E8734A;">
          ${sampleQIconSvg(19)}
          <span style="font-size:11.5px; font-weight:600; color:#44403C;">Sample Q&A</span>
        </button>
      </div>
      <div id="rzg-log" style="display:none; height:320px; overflow-y:auto; padding:12px; flex-direction:column; gap:4px; background:#ECE5DD;"></div>
      <form id="rzg-inputBar" style="display:none; gap:8px; padding:10px 12px; background:#fff; border-top:1px solid rgba(0,0,0,.06);">
        <input type="text" id="rzg-input" placeholder="Ask about this page..." autocomplete="off"
               style="flex:1; padding:9px 12px; border-radius:18px; border:1px solid #E5E7EB; background:#F7F7F8; font-size:13.5px; outline:none;">
        <button type="submit" style="background:#E8734A; color:#fff; border:none; border-radius:50%; width:36px; height:36px; cursor:pointer; flex-shrink:0;">➤</button>
        <button type="button" id="rzg-micBtn" title="Click to talk"
                style="background:#F1F0EE; color:#57534E; border:1px solid #E7E5E4; border-radius:50%; width:36px; height:36px; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center;">${micIconSvg(17)}</button>
      </form>`;

    injectMicStyles();
    injectChatStyles();
    document.body.appendChild(wrap);

    // Shared close/minimize logic - used by the header "−" button AND by
    // voice/text close-command detection (see isCloseCommand in initWidget).
    function closeWidget() {
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      wrap.style.display = "none";
      launcher.style.display = "flex";
    }
    wrap.__rzgClose = closeWidget;

    // Open on launcher tap, minimize back to the launcher on header's "−".
    launcher.addEventListener("click", () => {
      wrap.style.display = "block";
      launcher.style.display = "none";
    });
    wrap.querySelector("#rzg-minimizeBtn").addEventListener("click", closeWidget);

    return wrap;
  }

  function initWidget() {
    const wrap = buildWidget();
    const log = wrap.querySelector("#rzg-log");
    const form = wrap.querySelector("#rzg-inputBar");
    const input = wrap.querySelector("#rzg-input");
    const micBtn = wrap.querySelector("#rzg-micBtn");
    const langGate = wrap.querySelector("#rzg-langGate");
    const quickActions = wrap.querySelector("#rzg-quickActions");

    // The session's chosen content/UI language ("hi" or "en") - null until
    // the user picks one on the language gate. Everything downstream
    // (button labels, status text, and every request's `language` field)
    // reads from this instead of the previous hardcoded "auto"/Hindi text.
    let sessionLanguage = null;
    function t(key) {
      return (UI_TEXT[sessionLanguage] || UI_TEXT.hi)[key];
    }

    function applyLanguageToChrome() {
      const btnRead = wrap.querySelector("#rzg-btnRead");
      const btnSummary = wrap.querySelector("#rzg-btnSummary");
      const btnSample = wrap.querySelector("#rzg-btnSample");
      btnRead.title = t("readTitle");
      btnRead.querySelector("span").textContent = t("readLabel");
      btnSummary.title = t("summaryTitle");
      btnSummary.querySelector("span").textContent = t("summaryLabel");
      btnSample.title = t("sampleTitle");
      btnSample.querySelector("span").textContent = t("sampleLabel");
      input.placeholder = t("placeholder");
    }

    function selectLanguage(lang) {
      sessionLanguage = lang;
      langGate.style.display = "none";
      quickActions.style.display = "flex";
      log.style.display = "flex";
      form.style.display = "flex";
      applyLanguageToChrome();
      addMessage(t("welcome"), "bot");
    }

    wrap.querySelector("#rzg-langHi").addEventListener("click", () => selectLanguage("hi"));
    wrap.querySelector("#rzg-langEn").addEventListener("click", () => selectLanguage("en"));

    function addMessage(text, who) {
      const row = document.createElement("div");
      row.className = "rzg-bubble-row";
      row.style.justifyContent = who === "user" ? "flex-end" : "flex-start";

      const bubble = document.createElement("div");
      bubble.className = who === "user" ? "rzg-bubble rzg-bubble-user" : "rzg-bubble rzg-bubble-bot";

      const textSpan = document.createElement("span");
      textSpan.textContent = text;
      bubble.appendChild(textSpan);

      const time = document.createElement("span");
      time.className = "rzg-bubble-time";
      time.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      bubble.appendChild(time);

      row.appendChild(bubble);
      log.appendChild(row);
      log.scrollTop = log.scrollHeight;
      return bubble;
    }

    // Fires when the user's typed or spoken message is a close/stop
    // command (see isCloseCommand). Shows + speaks a short farewell, then
    // minimizes the widget back to the launcher bubble once the farewell
    // finishes speaking (falls back to a fixed delay if speech synthesis
    // isn't available, e.g. some in-app browsers).
    function handleCloseCommand() {
      const farewell = t("closingReply");
      const botDiv = addMessage(farewell, "bot");
      botDiv.title = t("clickToHear");
      botDiv.onclick = () => speakText(farewell, sessionLanguage);

      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(farewell);
        if (sessionLanguage && sessionLanguage !== "auto") utterance.lang = sessionLanguage;
        utterance.onend = () => wrap.__rzgClose();
        utterance.onerror = () => wrap.__rzgClose();
        window.speechSynthesis.speak(utterance);
        // Safety net in case onend/onerror never fire on some browsers.
        setTimeout(() => wrap.__rzgClose(), 6000);
      } else {
        setTimeout(() => wrap.__rzgClose(), 1200);
      }
    }

    // Renders the backend's suggested_questions as clickable chips. Tapping
    // one fills the input and submits it, same as typing it by hand.
    function addSuggestedQuestions(questions) {
      if (!questions || !questions.length) return;
      const row = document.createElement("div");
      row.style.cssText = "display:flex; flex-wrap:wrap; gap:6px; padding:2px 2px 6px;";
      questions.forEach((q) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.textContent = q;
        chip.style.cssText = "background:#fff; border:1px solid #E5E7EB; border-radius:14px; padding:6px 10px; font-size:12px; color:#57534E; cursor:pointer; text-align:left;";
        chip.addEventListener("click", () => {
          input.value = q;
          form.dispatchEvent(new Event("submit", { cancelable: true }));
        });
        row.appendChild(chip);
      });
      log.appendChild(row);
      log.scrollTop = log.scrollHeight;
    }

    // Renders sample Q&A as numbered chips (numbers work regardless of
    // reading ability). Tapping one re-plays that question + answer aloud.
    function addSampleQuestions(qaItems, language) {
      if (!qaItems || !qaItems.length) return;
      const row = document.createElement("div");
      row.style.cssText = "display:flex; flex-wrap:wrap; gap:6px; padding:2px 2px 6px;";
      qaItems.forEach((qa, i) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.innerHTML = `<span style="display:flex; color:#A8A29E;">${speakerIconSvg(13)}</span><span>${t("sampleChipLabel")} ${i + 1}</span>`;
        chip.title = qa.question;
        chip.style.cssText = "display:flex; align-items:center; gap:4px; background:#fff; border:1px solid #E5E7EB; border-radius:14px; padding:6px 10px; font-size:12px; color:#57534E; cursor:pointer; text-align:left;";
        chip.addEventListener("click", () => {
          addMessage(qa.question, "user");
          const ansDiv = addMessage(qa.answer, "bot");
          ansDiv.title = "सुनने के लिए यहाँ दोबारा क्लिक करें";
          ansDiv.onclick = () => speakText(qa.answer, language);
          speakText(qa.answer, language);
        });
        row.appendChild(chip);
      });
      log.appendChild(row);
      log.scrollTop = log.scrollHeight;
    }

    // Disables a quick-action button and shows a busy label while its
    // request is in flight, so an illiterate user can't double-tap it and
    // trigger two overlapping voice replies.
    function withBusyButton(btn, busyLabel, idleLabel, fn) {
      return async () => {
        if (btn.disabled) return;
        btn.disabled = true;
        btn.style.opacity = "0.5";
        const labelEl = btn.querySelector("span:last-child");
        const original = labelEl.textContent;
        labelEl.textContent = busyLabel;
        try {
          await fn();
        } finally {
          btn.disabled = false;
          btn.style.opacity = "1";
          labelEl.textContent = idleLabel || original;
        }
      };
    }

    const btnRead = wrap.querySelector("#rzg-btnRead");
    const btnSummary = wrap.querySelector("#rzg-btnSummary");
    const btnSample = wrap.querySelector("#rzg-btnSample");

    btnRead.addEventListener("click", withBusyButton(btnRead, "...", "", async () => {
      const labelEl = btnRead.querySelector("span:last-child");
      const idle = t("readLabel");
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      const text = extractCurrentModuleText();
      if (!text || text.trim().length < MIN_USEFUL_CONTENT_CHARS) {
        addMessage(t("nothingToRead"), "bot");
        labelEl.textContent = idle;
        return;
      }
      addMessage(t("readingNow"), "bot");
      try {
        if (sessionLanguage && sessionLanguage !== "en") {
          // The browser's speechSynthesis only changes voice/accent via
          // utterance.lang - it never translates the words themselves, so
          // a Hindi session needs the text translated server-side first
          // (reuses the same read_content -> llm.translate path /chat/
          // already uses for "read this page" requests).
          const res = await fetch(`${CONFIG.BACKEND_URL}/chat/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: "read this page",
              language: sessionLanguage,
              page_url: location.href,
              page_content: text,
            }),
          });
          if (!res.ok) throw new Error(`Read failed: ${res.status}`);
          const data = await res.json();
          speakText(data.reply, data.language);
        } else {
          speakText(text, "en");
        }
      } catch (err) {
        // Fall back to reading the original text rather than staying
        // silent if the translation call fails.
        speakText(text, sessionLanguage || "auto");
      }
      labelEl.textContent = idle;
    }));

    btnSummary.addEventListener("click", withBusyButton(btnSummary, "...", "", async () => {
      const labelEl = btnSummary.querySelector("span:last-child");
      const idle = t("summaryLabel");
      const text = extractCurrentModuleText();
      if (!text || text.trim().length < MIN_USEFUL_CONTENT_CHARS) {
        addMessage(t("notEnoughForSummary"), "bot");
        labelEl.textContent = idle;
        return;
      }
      const statusDiv = addMessage(t("summaryPreparing"), "bot");
      try {
        const res = await fetch(`${CONFIG.BACKEND_URL}/summarize/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, length: "short", language: sessionLanguage || "auto" }),
        });
        if (!res.ok) throw new Error(`Summarize failed: ${res.status}`);
        const data = await res.json();
        statusDiv.textContent = data.summary;
        statusDiv.title = t("clickToHear");
        statusDiv.onclick = () => speakText(data.summary, data.language);
        speakText(data.summary, data.language);
      } catch (err) {
        statusDiv.textContent = t("summaryFailed");
      } finally {
        labelEl.textContent = idle;
      }
    }));

    btnSample.addEventListener("click", withBusyButton(btnSample, "...", "", async () => {
      const labelEl = btnSample.querySelector("span:last-child");
      const idle = t("sampleLabel");
      const text = extractCurrentModuleText();
      if (!text || text.trim().length < MIN_USEFUL_CONTENT_CHARS) {
        addMessage(t("notEnoughForSample"), "bot");
        labelEl.textContent = idle;
        return;
      }
      const statusDiv = addMessage(t("samplePreparing"), "bot");
      try {
        const res = await fetch(`${CONFIG.BACKEND_URL}/suggestions/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, count: 4, language: sessionLanguage || "auto" }),
        });
        if (!res.ok) throw new Error(`Suggestions failed: ${res.status}`);
        const data = await res.json();
        if (!data.questions || !data.questions.length) {
          statusDiv.textContent = t("sampleNone");
          return;
        }
        statusDiv.textContent = t("sampleReady");
        addSampleQuestions(data.questions, data.language);
        const toSpeak = [];
        data.questions.forEach((qa, i) => {
          toSpeak.push(`${i + 1}. ${qa.question}`);
          toSpeak.push(qa.answer);
        });
        speakQueue(toSpeak, data.language);
      } catch (err) {
        statusDiv.textContent = t("sampleFailed");
      } finally {
        labelEl.textContent = idle;
      }
    }));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const message = input.value.trim();
      if (!message) return;
      addMessage(message, "user");
      input.value = "";

      if (isCloseCommand(message)) {
        handleCloseCommand();
        return;
      }

      try {
        // Try the page-intent shortcuts first (summarize / read module).
        const intentResult = await tryHandlePageIntent(message, sessionLanguage || "auto");
        if (intentResult) {
          if (intentResult.type === "summarize") {
            const botDiv = addMessage(intentResult.result.summary, "bot");
            botDiv.title = t("clickToHear");
            botDiv.onclick = () => speakText(intentResult.result.summary, intentResult.result.language);
          } else if (intentResult.type === "read_module") {
            addMessage(intentResult.result.transcript || `Reading: ${intentResult.result.module_title}`, "bot");
          }
          return;
        }
      } catch (intentErr) {
        console.warn("Page-intent handling failed, falling back to /chat/:", intentErr);
      }

      try {
        const res = await fetch(`${CONFIG.BACKEND_URL}/chat/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            language: sessionLanguage || "auto",
            page_url: location.href,
            page_content: extractPageContent(),
          }),
        });
        const data = await res.json();
        const botDiv = addMessage(data.reply, "bot");
        botDiv.title = t("clickToHear");
        botDiv.onclick = () => speakText(data.reply, data.language);
        addSuggestedQuestions(data.suggested_questions);
      } catch (err) {
        addMessage(t("unreachable"), "bot");
      }
    });

    // ---- Voice input ----
    let mediaRecorder, audioChunks = [], isRecording = false;
    let recordStartedAt = 0;

    // Two separate timeouts, both auto-stop-and-act without needing another
    // click on the mic button:
    //   - NO_INPUT_MS: nothing at all has been heard yet (user hasn't
    //     started talking). Gives them a full 5s to start, then gives up
    //     and shows/speaks a "didn't hear anything" prompt instead of
    //     sending empty audio to the backend.
    //   - SILENCE_MS: the user WAS talking and has now paused. Auto-stops
    //     quickly and sends what was recorded - no click needed.
    // hasDetectedSpeech is what decides which of the two applies at any
    // moment: before the first real sound, NO_INPUT_MS governs; once real
    // speech is heard, SILENCE_MS takes over for the rest of the recording.
    const SILENCE_THRESHOLD = 0.015; // RMS level below which audio counts as silence
    const SILENCE_MS = 1400;         // how long a pause after speech must persist to auto-send
    const MIN_RECORD_MS = 700;       // minimum recording length before that auto-send can fire
    const NO_INPUT_MS = 5000;        // how long to wait for the user to say anything at all
    let audioCtx, analyserNode, silenceRafId, silenceStartedAt = null;
    let hasDetectedSpeech = false;
    // Set right before an auto-stop that should NOT send audio (currently
    // only the no-input case) - sendRecording() checks and clears this.
    let skipSendReason = null;

    function watchForSilence() {
      const data = new Uint8Array(analyserNode.fftSize);
      const tick = () => {
        if (!isRecording) return;
        analyserNode.getByteTimeDomainData(data);
        let sumSquares = 0;
        for (let i = 0; i < data.length; i++) {
          const normalized = (data[i] - 128) / 128;
          sumSquares += normalized * normalized;
        }
        const rms = Math.sqrt(sumSquares / data.length);
        const recordedFor = Date.now() - recordStartedAt;

        if (rms >= SILENCE_THRESHOLD) {
          hasDetectedSpeech = true;
          silenceStartedAt = null;
        } else if (!hasDetectedSpeech) {
          // Still waiting for the user to say their first word.
          if (recordedFor > NO_INPUT_MS) {
            skipSendReason = "no_input";
            stopRecording();
            return;
          }
        } else {
          // Already heard speech at least once - now watching for a pause
          // that means they're done talking.
          if (silenceStartedAt === null) silenceStartedAt = Date.now();
          const silentFor = Date.now() - silenceStartedAt;
          if (silentFor > SILENCE_MS && recordedFor > MIN_RECORD_MS) {
            stopRecording();
            return;
          }
        }
        silenceRafId = requestAnimationFrame(tick);
      };
      tick();
    }

    async function startRecording() {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];
      mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
      mediaRecorder.onstop = sendRecording;
      mediaRecorder.start();
      isRecording = true;
      recordStartedAt = Date.now();
      hasDetectedSpeech = false;
      skipSendReason = null;
      micBtn.classList.add("rzg-mic-recording");
      micBtn.title = "Listening... speak now (click to stop)";

      // Set up live volume monitoring so we can auto-stop on silence.
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      analyserNode = audioCtx.createAnalyser();
      analyserNode.fftSize = 512;
      source.connect(analyserNode);
      silenceStartedAt = null;
      watchForSilence();
    }

    function stopRecording() {
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      }
      isRecording = false;
      micBtn.classList.remove("rzg-mic-recording");
      micBtn.title = "Click to talk";
      if (silenceRafId) cancelAnimationFrame(silenceRafId);
      if (audioCtx) { audioCtx.close(); audioCtx = null; }
      analyserNode = null;
      silenceStartedAt = null;
    }

    async function sendRecording() {
      if (skipSendReason === "no_input") {
        skipSendReason = null;
        const msg = t("micNoInput");
        const botDiv = addMessage(msg, "bot");
        botDiv.title = t("clickToHear");
        botDiv.onclick = () => speakText(msg, sessionLanguage);
        speakText(msg, sessionLanguage);
        return;
      }

      const blob = new Blob(audioChunks, { type: "audio/webm" });
      const placeholder = addMessage("🎤 (transcribing...)", "user");

      const formData = new FormData();
      formData.append("audio", blob, "recording.webm");
      formData.append("page_url", location.href);
      formData.append("page_content", extractPageContent());
      formData.append("language", sessionLanguage || "auto");

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s safety net

      try {
        const res = await fetch(`${CONFIG.BACKEND_URL}/voice/chat`, {
          method: "POST",
          body: formData,
          signal: controller.signal,
        });
        clearTimeout(timeoutId);
        const data = await res.json();

        if (!res.ok) {
          placeholder.textContent = data.transcript || "(transcription unavailable)";
          addMessage(data.detail || t("unreachable"), "bot");
          return;
        }

        placeholder.textContent = data.transcript;

        if (isCloseCommand(data.transcript)) {
          handleCloseCommand();
          return;
        }

        const botDiv = addMessage(data.reply, "bot");
        if (data.reply) {
          botDiv.title = t("clickToHear");
          botDiv.onclick = () => speakText(data.reply, data.language);
          speakText(data.reply, data.language); // autoplay the spoken reply
        }
        addSuggestedQuestions(data.suggested_questions);
      } catch (err) {
        clearTimeout(timeoutId);
        placeholder.textContent = "(transcription failed)";
        if (err.name === "AbortError") {
          addMessage(t("unreachable"), "bot");
        } else {
          addMessage(t("unreachable"), "bot");
        }
      }
    }

    micBtn.addEventListener("click", () => {
      // Cut off any reply the widget is currently speaking - the user is
      // about to talk, so it shouldn't keep talking over them.
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      if (isRecording) stopRecording(); else startRecording();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWidget);
  } else {
    initWidget();
  }
})();