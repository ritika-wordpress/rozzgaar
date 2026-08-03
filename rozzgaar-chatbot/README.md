# Rozzgaar Chatbot Backend

A FastAPI backend for a website chatbot that:

- Reads content from the **Rozzgaar API** (courses, bundles) and **scrapes**
  configured static pages (About, FAQ, Contact, etc.)
- Answers questions using **Groq** (fast Llama-family inference), grounded
  only in that content (basic RAG with TF-IDF retrieval)
- Gives **short** and **long** summaries of any course/bundle or pasted text
- Suggests **sample questions (with answers)** for a course or topic
- Speaks any reply in **Hindi or English** using free Microsoft **Edge TTS**
- Auto-detects Hindi vs English per message (Devanagari script check)

## 1. Setup

```bash
cd rozzgaar-chatbot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `GROQ_API_KEY` - get one free at https://console.groq.com/keys
- `STATIC_PAGE_URLS` - real URLs of your About/FAQ/Contact pages
- `ADMIN_SECRET` - any password you choose, protects the ingest endpoint
- `ALLOWED_ORIGINS` - your website's domain(s), for CORS

## 2. Build the knowledge base (first run, then periodically)

Start the server, then trigger a content refresh:

```bash
uvicorn app.main:app --reload --port 8000
```

```bash
curl -X POST http://localhost:8000/ingest/refresh \
  -H "X-Admin-Secret: change_me"
```

This pulls every live course + bundle from your API and scrapes the static
pages, chunks the text, and builds a TF-IDF index saved to `data/kb.joblib`.
Re-run this whenever course content changes (e.g. via a daily cron job or
after publishing a new course).

## 3. Try it

Open `static/test-widget.html` in a browser (update `API_BASE` if not on
localhost:8000), or use the interactive API docs at `http://localhost:8000/docs`.

### Chat
```
POST /chat/
{ "message": "instagram marketing course kitne din ka hai?", "language": "auto" }
```
Returns a grounded reply, the detected language, source titles/links used,
and 2-3 follow-up question suggestions.

### Summarize a course
```
POST /summarize/
{ "course_slug": "instagram-marketing", "length": "short", "language": "en" }
```
`length` is `"short"` (2-3 sentences) or `"long"` (~250 words, structured).
You can also pass raw `"text"` instead of a slug to summarize any pasted content.

### Suggested questions
```
POST /suggestions/
{ "course_slug": "instagram-marketing", "count": 5, "language": "auto" }
```
Returns `{"questions": [{"question": "...", "answer": "..."}], "language": "en"}`.

### Text-to-speech (voice output)
```
POST /tts/speak
{ "text": "Namaste! Yeh course 4 hafton ka hai.", "language": "auto" }
```
Returns raw `audio/mpeg` bytes (play directly, or save as `.mp3`).
Voices used by default: `hi-IN-SwaraNeural` (Hindi), `en-IN-NeerjaNeural`
(English) - both configurable in `.env`. Run `edge-tts --list-voices` to see
every available voice.

### Speech-to-text (voice input)
```
POST /stt/transcribe   (multipart/form-data)
  audio: <recorded file - webm/mp3/wav/m4a>
  language_hint: "en" | "hi"   (optional)
```
Returns `{"transcript": "...", "language": "en"}`. Uses Groq's hosted Whisper
(`whisper-large-v3-turbo` by default) - same API key as chat, no extra signup.
Use this if you just want the transcript back (e.g. to drop into a text box).

### Full voice round trip (input -> chat -> spoken reply, one call)
```
POST /voice/chat   (multipart/form-data)
  audio: <recorded question>
```
Transcribes the question, runs it through the exact same grounded RAG
pipeline as `/chat/`, then speaks the reply back. Returns:
```json
{
  "transcript": "instagram marketing course kitne din ka hai?",
  "reply": "...",
  "language": "hi",
  "sources": [...],
  "suggested_questions": [...],
  "audio_base64": "<mp3 bytes, base64>",
  "audio_mime": "audio/mpeg"
}
```
Decode `audio_base64` and autoplay it in the browser - see the mic button in
`static/test-widget.html` for a working example (hold to record, release to
send; the reply plays automatically).

## 4. Architecture notes

- `app/services/content_fetcher.py` - talks to your Rozzgaar API and
  scrapes static pages with BeautifulSoup.
- `app/services/knowledge_base.py` - chunks text (~180 words/chunk) and
  retrieves relevant chunks via TF-IDF cosine similarity. This is deliberately
  lightweight (no GPU/embedding model needed). If your content grows large or
  you want semantic (not just keyword) matching, swap this module for
  `sentence-transformers` + a vector DB (Chroma/FAISS) - no other file needs
  to change since routers only call `kb.retrieve()` / `kb.get_full_doc()`.
- `app/services/llm.py` - all Groq prompt calls (chat answer, summarize,
  suggested Q&A). System prompts instruct the model to answer only from
  supplied context, so it won't invent prices or policies.
- `app/services/language.py` - Devanagari-script heuristic for hi/en
  detection. Good for Hindi typed in Devanagari; romanized Hindi ("Hinglish")
  is treated as English - swap in a proper language-ID model later if needed.
- `app/services/tts.py` - Edge TTS wrapper, no API key required.

## 5. Deploying

Any standard ASGI host works (Render, Railway, a VPS with `uvicorn`/`gunicorn`
+ nginx, etc.). Put the real `ALLOWED_ORIGINS` (your website domain) in
`.env`, run `/ingest/refresh` once after each deploy, and consider a cron job
to refresh the knowledge base on a schedule so new courses show up automatically.

Embed on the website by pointing your existing chat widget's JS at the
deployed API base URL and reusing the fetch calls in `static/test-widget.html`.
