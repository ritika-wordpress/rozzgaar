import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.limiter import limiter
from app.routers import chat, ingest, module_read, stt, suggestions, summarize, tts, voice
from app.services.knowledge_base import kb

# edge-tts (used by app/services/tts.py) relies on the `websockets` library
# for its handshake with Microsoft's speech endpoint. On Windows, asyncio's
# default ProactorEventLoop is known to hang indefinitely with that library
# instead of failing fast - which shows up exactly as "TTS timed out after
# 12s" on every single call, even though plain HTTPS (e.g. curl) reaches the
# same host fine. Forcing the selector loop is the standard fix. This only
# affects Windows; other platforms are unaffected.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Rozzgaar Chatbot API",
    description="Chat, summarization, suggested-questions, and Hindi/English "
                 "text-to-speech for the Rozzgaar website.",
    version="1.0.0",
)

# Rate limiting - protects the LLM/TTS/STT endpoints from abuse (and your
# Groq bill) and slows brute-force attempts against the admin-secret header
# on /ingest/refresh. Limits are set per-router below.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serves embed.js with CONFIG.BACKEND_URL swapped for whatever
# PUBLIC_BACKEND_URL is currently set to in .env - so updating the ngrok
# URL only ever means editing .env and restarting, never hand-editing the
# JS file. Registered BEFORE the /static mount below so it wins for this
# one path; every other file in ./static (page-intent.js, test-widget.html)
# still falls through to the plain static mount untouched.
_EMBED_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "embed.js"
_EMBED_JS_PLACEHOLDER = 'BACKEND_URL: "https://tropical-refocus-exact.ngrok-free.dev",'


@app.get("/static/embed.js")
def embed_js():
    content = _EMBED_JS_PATH.read_text(encoding="utf-8")
    content = content.replace(
        _EMBED_JS_PLACEHOLDER,
        f'BACKEND_URL: "{settings.public_backend_url}",',
    )
    return Response(content=content, media_type="application/javascript")


# Serves everything else in ./static — page-intent.js, test-widget.html,
# etc. — at https://<ngrok-url>/static/<filename>.
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(chat.router)
app.include_router(summarize.router)
app.include_router(suggestions.router)
app.include_router(tts.router)
app.include_router(stt.router)
app.include_router(voice.router)
app.include_router(module_read.router)
app.include_router(ingest.router)


@app.on_event("startup")
def startup():
    if not kb.load():
        logging.info("No cached knowledge base found on disk yet. "
                      "Call POST /ingest/refresh (with X-Admin-Secret header) to build one.")
    else:
        logging.info("Knowledge base loaded from disk: %d chunks.", len(kb.chunks))


@app.get("/")
def health():
    return {
        "status": "ok",
        "knowledge_base_chunks": len(kb.chunks),
        "docs_url": "/docs",
    }
