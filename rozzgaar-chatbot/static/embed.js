/**
 * embed.js - Rozzgaar Assistant widget
 * -----------------------------------------------------------------------
 * Drop this ONE script tag into course-content.php (near the end of
 * <body>, after the page's own inline <script> block). Because
 * course-content.php is already slug-agnostic (course is picked from
 * ?slug=... at runtime), adding it there once makes the widget appear
 * on every course page automatically - no per-course wiring needed.
 *
 *   <script defer src="https://api.rozzgaar.in/static/embed.js"></script>
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
    BACKEND_URL: "https://api.rozzgaar.in",  // public backend URL (App Runner / ALB / CloudFront)
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
  // Rozzgaar logo mark (the rupee + growth-arrow icon cropped from the
  // brand logo), embedded as a base64 data URI so the widget needs zero
  // extra network requests. Replaces the old plain robot glyph.
  // Rozzgaar logo mark (rupee + growth-arrow icon), embedded as a base64
  // PNG data URI so the widget needs zero extra network requests. This
  // string was generated programmatically (base64 -w0) from the uploaded
  // logo file - never hand-edit/retype this string, a single changed
  // character will silently corrupt the image with no visible error.
  const ROZZGAAR_ICON_B64 = "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";
  function assistantIconSvg(size) {
    return `<img src="data:image/png;base64,${ROZZGAAR_ICON_B64}" width="${size}" height="${size}" alt="Rozzgaar" style="display:block; object-fit:contain;">`;
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
  // Filled paper-plane glyph for the send button - replaces the plain "➤"
  // text character so the send button matches the line-art icon language
  // used everywhere else in the widget (emoji/text glyphs render
  // inconsistently across OS fonts).
  function sendIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 11.5L20.5 4L13 20.5L10.8 13.2L3 11.5Z" fill="currentColor"/>
      </svg>`;
  }
  // Speech-bubble icon (three dots) used in the launcher's hover tooltip
  // to represent "ask a question" - same silhouette family as
  // sampleQIconSvg so the tooltip's icon row reads as one consistent set.
  function chatIconSvg(size) {
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4.5 5.8c0-1.2 1-2.2 2.2-2.2h10.6c1.2 0 2.2 1 2.2 2.2v8.6c0 1.2-1 2.2-2.2 2.2H9.4L6 19.9v-3.3h-.3c-1.2 0-2.2-1-2.2-2.2V5.8Z"
              stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <circle cx="8.3" cy="10" r="1" fill="currentColor"/>
        <circle cx="12" cy="10" r="1" fill="currentColor"/>
        <circle cx="15.7" cy="10" r="1" fill="currentColor"/>
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
        background:
          radial-gradient(circle at 15% 8%, rgba(192,57,43,0.05), transparent 45%),
          #F5F1EC;
      }
      #rzg-log::-webkit-scrollbar { width: 6px; }
      #rzg-log::-webkit-scrollbar-track { background: transparent; }
      #rzg-log::-webkit-scrollbar-thumb { background: rgba(192,57,43,0.25); border-radius: 10px; }
      #rzg-log::-webkit-scrollbar-thumb:hover { background: rgba(192,57,43,0.45); }

      .rzg-bubble-row { display: flex; margin: 3px 0; animation: rzg-bubble-in .22s ease both; }
      @keyframes rzg-bubble-in {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0); }
      }
      .rzg-bubble {
        position: relative;
        max-width: 80%;
        padding: 8px 11px 9px 11px;
        font-size: 13.5px;
        line-height: 1.42;
        box-shadow: 0 1px 2px rgba(0,0,0,.06), 0 1px 1px rgba(0,0,0,.04);
        word-wrap: break-word;
        white-space: pre-wrap;
        transition: transform .12s ease, box-shadow .12s ease;
      }
      .rzg-bubble-user {
        margin-left: auto;
        background: linear-gradient(135deg, #FDE9DE 0%, #FBDCCB 100%);
        border-radius: 14px 14px 3px 14px;
        color: #2b1a13;
      }
      .rzg-bubble-bot {
        margin-right: auto;
        background: #ffffff;
        border-radius: 14px 14px 14px 3px;
        color: #262220;
        cursor: pointer;
        border: 1px solid rgba(0,0,0,0.04);
      }
      .rzg-bubble-bot:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 10px rgba(0,0,0,.08);
      }
      .rzg-bubble-time {
        display: block;
        text-align: right;
        font-size: 10px;
        color: rgba(0,0,0,.4);
        margin-top: 3px;
        margin-left: 8px;
        float: right;
      }
    `;
    document.head.appendChild(style);
  }


  // Injects the pulsing "listening" animation once per page. Applied to
  // #rzg-micBtn via the .rzg-mic-recording class while recording is active.
  // Loads the "Varela Round" Google Font (matches the rounded lettering in
  // the Rozzgaar logo) once per page, so the widget title can use it.
  function injectBrandFont() {
    if (document.getElementById("rzg-font-link")) return;
    const link = document.createElement("link");
    link.id = "rzg-font-link";
    link.rel = "stylesheet";
    link.href = "https://fonts.googleapis.com/css2?family=Varela+Round&display=swap";
    document.head.appendChild(link);
  }

  // Core visual-polish stylesheet: launcher glow/hover, panel open/close
  // animation, quick-action + input hover/focus states. Kept separate
  // from injectChatStyles (message bubbles) and injectMicStyles
  // (recording indicator) so each stylesheet has one clear job.
  function injectWidgetStyles() {
    if (document.getElementById("rzg-widget-styles")) return;
    const style = document.createElement("style");
    style.id = "rzg-widget-styles";
    style.textContent = `
      @keyframes rzg-launcher-glow {
        0%, 100% { box-shadow: 0 8px 20px rgba(192,57,43,0.22), 0 0 0 0 rgba(192,57,43,0.28); }
        50%      { box-shadow: 0 8px 24px rgba(192,57,43,0.32), 0 0 0 7px rgba(192,57,43,0); }
      }
      #rzg-launcher {
        animation: rzg-launcher-glow 2.6s ease-in-out infinite;
        transition: transform .18s ease;
      }
      #rzg-launcher:hover { transform: scale(1.07); }
      #rzg-launcher:active { transform: scale(0.97); }

      #rzg-chat-widget {
        opacity: 0;
        transform: translateY(14px) scale(0.96);
        transition: opacity .2s ease, transform .2s ease;
        pointer-events: none;
      }
      #rzg-chat-widget.rzg-open {
        opacity: 1;
        transform: translateY(0) scale(1);
        pointer-events: auto;
      }

      #rzg-minimizeBtn { transition: background .15s ease, transform .15s ease; }
      #rzg-minimizeBtn:hover { background: rgba(255,255,255,.4) !important; transform: rotate(90deg); }

      #rzg-langHi, #rzg-langEn {
        transition: background .15s ease, color .15s ease, transform .15s ease, box-shadow .15s ease;
      }
      #rzg-langHi:hover, #rzg-langEn:hover {
        background: #c0392b !important; color: #fff !important;
        transform: translateY(-1px); box-shadow: 0 4px 10px rgba(192,57,43,0.28);
      }

      #rzg-quickActions button {
        transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
      }
      #rzg-quickActions button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 14px rgba(0,0,0,.09);
        background: #FFF7F5 !important;
      }
      #rzg-quickActions button:active { transform: translateY(0) scale(.97); }
      #rzg-quickActions button svg { transition: transform .15s ease; }
      #rzg-quickActions button:hover svg { transform: scale(1.1); }

      #rzg-langHi:active, #rzg-langEn:active { transform: translateY(0) scale(.97); }

      @media (max-width: 420px) {
        #rzg-launcher-tip { right: 10px !important; left: 10px !important; width: auto !important; }
      }

      #rzg-inputBar {
        transition: box-shadow .15s ease;
      }
      #rzg-input {
        transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
      }
      #rzg-input:focus {
        border-color: #c0392b !important;
        background: #fff !important;
        box-shadow: 0 0 0 3px rgba(192,57,43,0.12);
      }
      #rzg-inputBar button[type="submit"] {
        transition: transform .15s ease, box-shadow .15s ease;
      }
      #rzg-inputBar button[type="submit"]:hover {
        transform: scale(1.08);
        box-shadow: 0 4px 12px rgba(192,57,43,0.35);
      }
      #rzg-micBtn { transition: transform .15s ease, background .15s ease, color .15s ease, border-color .15s ease; }
      #rzg-micBtn:hover:not(.rzg-mic-recording) {
        background: #FFF0EC !important; color: #c0392b !important; border-color: #EFC7BE !important;
      }

      .rzg-suggest-chip, .rzg-sample-chip {
        transition: transform .12s ease, box-shadow .12s ease, background .12s ease;
      }
      .rzg-suggest-chip:hover, .rzg-sample-chip:hover {
        transform: translateY(-1px);
        box-shadow: 0 3px 8px rgba(0,0,0,.08);
        background: #FFF7F5 !important;
        border-color: #EFC7BE !important;
      }
    `;
    document.head.appendChild(style);
  }

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
        background: #c0392b !important;
        color: #fff !important;
        border-color: #c0392b !important;
        animation: rzg-mic-bounce 1s ease-in-out infinite;
      }
      #rzg-micBtn.rzg-mic-recording::before,
      #rzg-micBtn.rzg-mic-recording::after {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 2px solid #c0392b;
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
      launcherTooltip: "रोज़गार सहायक - सवाल पूछें, पेज का सारांश पाएं, और जवाब सुनें (हिंदी/English)",
      tipHeading: "मैं यह कर सकता हूँ:",
      tipAsk: "पेज के बारे में सवाल पूछें",
      tipRead: "पेज को ज़ोर से पढ़ें",
      tipSummary: "पेज का सारांश सुनें",
      tipSample: "नमूना सवाल-जवाब सुनें",
      tipVoice: "आवाज़ से बात करें",
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
      hoverToHear: "सुनने के लिए यहाँ माउस ले जाएँ",
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
      launcherTooltip: "Rozzgaar Assistant - ask questions, get page summaries, and hear answers aloud (Hindi/English)",
      tipHeading: "Here's what I can do:",
      tipAsk: "Answer questions about this page",
      tipRead: "Read the page aloud",
      tipSummary: "Summarize the page",
      tipSample: "Suggest sample Q&A",
      tipVoice: "Talk to me by voice",
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
      hoverToHear: "Hover here to hear this",
      placeholder: "Ask about this page...",
      unreachable: "Could not reach the assistant right now - please try again in a moment.",
      closingReply: "Thank you for your time. Feel free to connect anytime! 👋",
      micNoInput: "I didn't hear anything - tap the mic button to try again.",
    },
  };

  // Picks which UI_TEXT set (hi/en) to use for the launcher's hover
  // tooltip, based on the visitor's browser/OS language setting. Used as
  // a fallback only - see detectLauncherUiLang() below, which prefers the
  // page's own declared/visible language over this. Only hi/en are
  // supported UI languages (same as the rest of the widget and backend),
  // so anything else falls back to English - matches
  // app/services/language.py's existing hi/en scope.
  function detectBrowserUiLang() {
    const raw = (navigator.language || navigator.userLanguage || "en").toLowerCase();
    return raw.startsWith("hi") ? "hi" : "en";
  }

  // Detects the CONTENT language of the current page (e.g. is
  // course-content.php currently rendering the Hindi or English version of
  // the course), so the launcher's hover tooltip/speech matches what's
  // actually on screen instead of the visitor's browser/OS setting - a
  // Hindi-OS visitor reading an English page should still hear "English"
  // spoken, and vice versa. Checked in priority order:
  //   1. A Devanagari-script sniff of the actual rendered course/page
  //      content (via extractPageContent(), the same extraction used for
  //      Read/Summarize) - this is checked FIRST and wins over the <html
  //      lang> attribute below, because many sites set <html lang="en">
  //      as a fixed, site-wide value that never changes even when the
  //      *content* itself (course-content.php's Hindi vs English version,
  //      picked by ?slug=) is actually in Hindi. Trusting a static lang
  //      attribute over the real text on screen was the original bug.
  //   2. The standard <html lang="..."> attribute, only used if the
  //      content sample above was empty or had no clear script signal.
  //   3. detectBrowserUiLang(), as a last resort.
  const DEVANAGARI_RE = /[\u0900-\u097F]/g;
  const LATIN_WORD_RE = /[A-Za-z]{3,}/g;
  function detectLauncherUiLang() {
    const sample = (extractPageContent() || "").slice(0, 3000);
    if (sample) {
      const devanagariHits = (sample.match(DEVANAGARI_RE) || []).length;
      if (devanagariHits > 5) return "hi";
      const latinHits = (sample.match(LATIN_WORD_RE) || []).length;
      if (latinHits > 15) return "en"; // confidently Latin/English content
    }

    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    if (htmlLang.startsWith("hi")) return "hi";
    if (htmlLang.startsWith("en")) return "en";

    return detectBrowserUiLang();
  }

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

  // Hover-to-speak: speech starts on mouseenter and is cancelled on
  // mouseleave, so moving off the element early cuts the reading off
  // immediately rather than letting it finish. Replaces the old
  // click-to-hear replay pattern on bot bubbles. getText/getLang may be
  // plain values or zero-arg functions (so callers can defer evaluation
  // to hover time if needed).
  function attachHoverToSpeak(el, getText, getLang) {
    el.addEventListener("mouseenter", () => {
      const text = typeof getText === "function" ? getText() : getText;
      const lang = typeof getLang === "function" ? getLang() : getLang;
      speakText(text, lang);
    });
    el.addEventListener("mouseleave", () => {
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
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
    const launcherTooltipText = UI_TEXT[detectLauncherUiLang()].launcherTooltip;
    launcher.title = launcherTooltipText;
    launcher.setAttribute("aria-label", launcherTooltipText);
    // NOTE: launcher is 60px, circular. Icon bumped up slightly (32 -> 36)
    // for better visibility inside the button.
    launcher.style.cssText = `
      position:fixed; bottom:16px; right:16px; width:60px; height:60px;
      z-index:9999; background:#ffffff; border:2px solid #c0392b; border-radius:50%;
      box-shadow:0 8px 20px rgba(192,57,43,0.22); cursor:pointer;
      display:flex; align-items:center; justify-content:center; color:#fff;
      line-height:1;`;
    launcher.innerHTML = assistantIconSvg(36);
    document.body.appendChild(launcher);

    // Rich hover tooltip - shown above the launcher on mouseenter/focus so
    // a visitor knows what the assistant can do *before* they click to
    // open it. The plain `title` attribute above still exists as a
    // fallback (screen readers, browsers without hover), but it's slow to
    // appear and unstyled - this card is instant and matches the widget.
    const tipT = UI_TEXT[detectLauncherUiLang()];
    const tip = document.createElement("div");
    tip.id = "rzg-launcher-tip";
    tip.setAttribute("role", "tooltip");
    tip.style.cssText = `
      position:fixed; bottom:84px; right:16px; z-index:9998; width:238px;
      background:#ffffff; border-radius:14px; padding:14px 16px 13px;
      box-shadow:0 14px 34px rgba(0,0,0,.18), 0 4px 12px rgba(0,0,0,.08);
      border:1px solid rgba(192,57,43,.14);
      font-family:'Varela Round',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      transform-origin: bottom right;
      opacity:0; transform:translateY(18px) scale(.75); pointer-events:none;
      transition:opacity .22s cubic-bezier(.34,1.56,.64,1), transform .32s cubic-bezier(.34,1.56,.64,1);`;
    const tipRow = (icon, label) => `
      <div style="display:flex; align-items:center; gap:9px; font-size:12.5px; color:#44403C; padding:3px 0;">
        <span style="display:flex; flex-shrink:0; align-items:center; justify-content:center; width:22px; height:22px; border-radius:50%; background:#FBE7E2; color:#c0392b;">${icon}</span>
        <span>${label}</span>
      </div>`;
    tip.innerHTML = `
      <div style="font-weight:700; font-size:13px; color:#292524; margin-bottom:6px;">${tipT.tipHeading}</div>
      ${tipRow(chatIconSvg(13), tipT.tipAsk)}
      ${tipRow(readIconSvg(13), tipT.tipRead)}
      ${tipRow(summaryIconSvg(13), tipT.tipSummary)}
      ${tipRow(sampleQIconSvg(13), tipT.tipSample)}
      ${tipRow(micIconSvg(13), tipT.tipVoice)}
      <div style="position:absolute; bottom:-6px; right:22px; width:12px; height:12px; background:#fff; border-right:1px solid rgba(192,57,43,.14); border-bottom:1px solid rgba(192,57,43,.14); transform:rotate(45deg);"></div>`;
    document.body.appendChild(tip);
    // Force the browser to commit the hidden/shrunk starting state to the
    // page before any hover can fire - without this, a hover that happens
    // in the same paint frame the tip was created in can skip straight to
    // the end state instead of animating (the "shows but doesn't peek"
    // symptom: it appears, but the pop-out motion never plays).
    void tip.offsetHeight;

    function showLauncherTip() {
      tip.style.opacity = "1";
      tip.style.transform = "translateY(0) scale(1)";
    }
    function hideLauncherTip() {
      tip.style.opacity = "0";
      tip.style.transform = "translateY(18px) scale(.75)";
    }
    launcher.addEventListener("mouseenter", showLauncherTip);
    launcher.addEventListener("mouseleave", hideLauncherTip);
    launcher.addEventListener("focus", showLauncherTip);
    launcher.addEventListener("blur", hideLauncherTip);

    // Speak the launcher's description on hover, same content as the
    // visual tooltip above - this fires before the chat panel is even
    // open, so it uses the page's content language (detectLauncherUiLang)
    // rather than sessionLanguage, which doesn't exist yet at this point.
    launcher.addEventListener("mouseenter", () => {
      speakText(tipT.launcherTooltip, detectLauncherUiLang());
    });
    launcher.addEventListener("mouseleave", () => {
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    });

    const wrap = document.createElement("div");
    wrap.id = "rzg-chat-widget";
    wrap.style.cssText = `
      position:fixed; bottom:16px; right:16px; width:368px; max-width:calc(100vw - 32px);
      z-index:9999; background:#F5F1EC; border-radius:20px; overflow:hidden;
      box-shadow:0 20px 48px rgba(0,0,0,0.22), 0 4px 14px rgba(0,0,0,0.10);
      border:1px solid rgba(0,0,0,0.05);
      font-family:'Varela Round',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      display:block;`; // visibility handled by the rzg-open class (see injectWidgetStyles)
      // Base font-family cascades to every child (bubbles, buttons, chips,
      // input) that doesn't set its own - this is what makes the header's
      // "Varela Round" the widget-wide font instead of a header-only
      // accent. Devanagari text (हिंदी labels) still renders correctly:
      // browsers automatically fall through to the next font in the list
      // for glyphs Varela Round doesn't cover, so Hindi is unaffected.

    wrap.innerHTML = `
      <div style="background:linear-gradient(135deg, #d24a37 0%, #c0392b 55%, #a8321f 100%); color:#fff; padding:14px 16px; display:flex; align-items:center; gap:11px; box-shadow:0 2px 8px rgba(0,0,0,0.12);" id="rzg-header">
        <div style="width:34px;height:34px;border-radius:50%;background:#ffffff;border:1.5px solid rgba(255,255,255,.7);display:flex;align-items:center;justify-content:center;color:#fff;box-shadow:0 2px 6px rgba(0,0,0,0.15);">${assistantIconSvg(21)}</div>
        <div style="flex:1;">
          <div style="font-weight:600;font-size:15.5px;font-family:'Varela Round',-apple-system,sans-serif;letter-spacing:.2px;">Rozzgaar Assistant</div>
          <div style="font-size:11px;opacity:.9;display:flex;align-items:center;gap:4px;">
            <span style="width:6px;height:6px;border-radius:50%;background:#6EE7B7;display:inline-block;box-shadow:0 0 0 2px rgba(110,231,183,0.25);"></span>Online
          </div>
        </div>
        <button type="button" id="rzg-minimizeBtn" title="छोटा करें" aria-label="छोटा करें"
                style="background:rgba(255,255,255,.22); border:none; color:#fff; width:28px; height:28px; border-radius:50%; cursor:pointer; font-size:16px; line-height:1; flex-shrink:0;">−</button>
      </div>
      <div id="rzg-langGate" style="padding:26px 20px 26px; background:#F5F1EC; text-align:center;">
        <div style="font-weight:600; font-size:15px; color:#292524; margin-bottom:3px; font-family:'Varela Round',-apple-system,sans-serif;">भाषा चुनें / Choose language</div>
        <div style="font-size:12px; color:#8a8078; margin-bottom:18px;">कृपया अपनी पसंदीदा भाषा चुनें / Please select your preferred language</div>
        <div style="display:flex; gap:10px; justify-content:center;">
          <button type="button" id="rzg-langHi" style="flex:1; max-width:140px; background:linear-gradient(135deg,#FFF7F5,#FDEBE6); border:1.5px solid #c0392b; color:#c0392b; border-radius:14px; padding:13px 8px; font-size:14px; font-weight:700; letter-spacing:.2px; cursor:pointer; font-family:inherit; box-shadow:0 3px 8px rgba(192,57,43,.10);">हिंदी</button>
          <button type="button" id="rzg-langEn" style="flex:1; max-width:140px; background:linear-gradient(135deg,#FFF7F5,#FDEBE6); border:1.5px solid #c0392b; color:#c0392b; border-radius:14px; padding:13px 8px; font-size:14px; font-weight:700; letter-spacing:.2px; cursor:pointer; font-family:inherit; box-shadow:0 3px 8px rgba(192,57,43,.10);">English</button>
        </div>
      </div>
      <div id="rzg-quickActions" style="display:none; gap:8px; padding:12px 12px 0; background:#F5F1EC;">
        <button type="button" id="rzg-btnRead" title="Listen to this page read aloud"
                style="flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; background:#fff; border:1px solid #EFE9E2; border-radius:14px; padding:12px 4px; cursor:pointer; font-family:inherit; color:#c0392b; box-shadow:0 2px 8px rgba(0,0,0,.05);">
          <span style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#FDE4DC,#FBD0C2);box-shadow:inset 0 0 0 1px rgba(192,57,43,.12);display:flex;align-items:center;justify-content:center;">${readIconSvg(15)}</span>
          <span style="font-size:11.5px; font-weight:700; letter-spacing:.1px; color:#44403C;">Read</span>
        </button>
        <button type="button" id="rzg-btnSummary" title="Listen to a summary of this page"
                style="flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; background:#fff; border:1px solid #EFE9E2; border-radius:14px; padding:12px 4px; cursor:pointer; font-family:inherit; color:#c0392b; box-shadow:0 2px 8px rgba(0,0,0,.05);">
          <span style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#FDE4DC,#FBD0C2);box-shadow:inset 0 0 0 1px rgba(192,57,43,.12);display:flex;align-items:center;justify-content:center;">${summaryIconSvg(15)}</span>
          <span style="font-size:11.5px; font-weight:700; letter-spacing:.1px; color:#44403C;">Summary</span>
        </button>
        <button type="button" id="rzg-btnSample" title="Listen to sample questions and answers"
                style="flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; background:#fff; border:1px solid #EFE9E2; border-radius:14px; padding:12px 4px; cursor:pointer; font-family:inherit; color:#c0392b; box-shadow:0 2px 8px rgba(0,0,0,.05);">
          <span style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#FDE4DC,#FBD0C2);box-shadow:inset 0 0 0 1px rgba(192,57,43,.12);display:flex;align-items:center;justify-content:center;">${sampleQIconSvg(15)}</span>
          <span style="font-size:11.5px; font-weight:700; letter-spacing:.1px; color:#44403C;">Sample Q&A</span>
        </button>
      </div>
      <div id="rzg-log" style="display:none; height:320px; overflow-y:auto; padding:14px; flex-direction:column; gap:4px; background:#F5F1EC;"></div>
      <form id="rzg-inputBar" style="display:none; gap:8px; padding:12px 14px; background:#fff; border-top:1px solid rgba(0,0,0,.06);">
        <input type="text" id="rzg-input" placeholder="Ask about this page..." autocomplete="off"
               style="flex:1; padding:10px 16px; border-radius:22px; border:1.5px solid #E5E7EB; background:#F7F7F8; font-size:13.5px; font-family:inherit; outline:none;">
        <button type="submit" style="background:linear-gradient(135deg,#d24a37,#c0392b); color:#fff; border:none; border-radius:50%; width:40px; height:40px; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; box-shadow:0 3px 10px rgba(192,57,43,0.35);">${sendIconSvg(16)}</button>
        <button type="button" id="rzg-micBtn" title="Click to talk"
                style="background:#F1F0EE; color:#57534E; border:1px solid #E7E5E4; border-radius:50%; width:40px; height:40px; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; box-shadow:0 1px 4px rgba(0,0,0,.05);">${micIconSvg(17)}</button>
      </form>`;

    injectMicStyles();
    injectChatStyles();
    injectBrandFont();
    injectWidgetStyles();
    document.body.appendChild(wrap);

    // Shared close/minimize logic - used by the header "−" button AND by
    // voice/text close-command detection (see isCloseCommand in initWidget).
    // Toggles the rzg-open class (opacity/transform transition defined in
    // injectWidgetStyles) instead of an instant display swap, so the panel
    // fades + scales in/out smoothly rather than popping.
    function closeWidget() {
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      wrap.classList.remove("rzg-open");
      launcher.style.display = "flex";
      hideLauncherTip();
    }
    wrap.__rzgClose = closeWidget;

    // Open on launcher tap, minimize back to the launcher on header's "−".
    launcher.addEventListener("click", () => {
      hideLauncherTip();
      wrap.classList.add("rzg-open");
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
      btnRead.querySelector("span:last-child").textContent = t("readLabel");
      btnSummary.title = t("summaryTitle");
      btnSummary.querySelector("span:last-child").textContent = t("summaryLabel");
      btnSample.title = t("sampleTitle");
      btnSample.querySelector("span:last-child").textContent = t("sampleLabel");
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
      botDiv.title = t("hoverToHear");
      attachHoverToSpeak(botDiv, farewell, sessionLanguage);

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
        chip.className = "rzg-suggest-chip";
        chip.style.cssText = "background:#fff; border:1px solid #EFE9E2; border-radius:18px; padding:7px 13px; font-size:12px; font-family:inherit; color:#57534E; cursor:pointer; text-align:left; box-shadow:0 1px 3px rgba(0,0,0,.05);";
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
    // reading ability). Tapping one re-plays that question + answer aloud;
    // the resulting answer bubble also speaks again on hover.
    function addSampleQuestions(qaItems, language) {
      if (!qaItems || !qaItems.length) return;
      const row = document.createElement("div");
      row.style.cssText = "display:flex; flex-wrap:wrap; gap:6px; padding:2px 2px 6px;";
      qaItems.forEach((qa, i) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.innerHTML = `<span style="display:flex; color:#A8A29E;">${speakerIconSvg(13)}</span><span>${t("sampleChipLabel")} ${i + 1}</span>`;
        chip.title = qa.question;
        chip.className = "rzg-sample-chip";
        chip.style.cssText = "display:flex; align-items:center; gap:5px; background:#fff; border:1px solid #EFE9E2; border-radius:18px; padding:7px 13px; font-size:12px; font-family:inherit; font-weight:600; color:#57534E; cursor:pointer; text-align:left; box-shadow:0 1px 3px rgba(0,0,0,.05);";
        chip.addEventListener("click", () => {
          addMessage(qa.question, "user");
          const ansDiv = addMessage(qa.answer, "bot");
          ansDiv.title = t("hoverToHear");
          attachHoverToSpeak(ansDiv, qa.answer, language);
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
        statusDiv.title = t("hoverToHear");
        attachHoverToSpeak(statusDiv, data.summary, data.language);
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
            botDiv.title = t("hoverToHear");
            attachHoverToSpeak(botDiv, intentResult.result.summary, intentResult.result.language);
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
        botDiv.title = t("hoverToHear");
        attachHoverToSpeak(botDiv, data.reply, data.language);
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
        botDiv.title = t("hoverToHear");
        attachHoverToSpeak(botDiv, msg, sessionLanguage);
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
          botDiv.title = t("hoverToHear");
          attachHoverToSpeak(botDiv, data.reply, data.language);
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