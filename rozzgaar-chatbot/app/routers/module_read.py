import logging
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.limiter import limiter
from app.services.content_fetcher import fetch_course_contents
from app.services.language import resolve_language
from app.services.llm import translate

router = APIRouter(prefix="/modules", tags=["modules"])
logger = logging.getLogger(__name__)


class ModuleReadRequest(BaseModel):
    course_slug: str
    module_query: str            # e.g. "module 1", or a free-text module title
    language: str = "auto"       # "auto" | "en" | "hi"  - same convention as your TTSRequest
    voice: str | None = None     # optional override, same as TTSRequest
    # The user's own request text (e.g. "module 2 padho hindi mein"). Used
    # to resolve language="auto" - falls back to module_query if omitted,
    # but the widget often sets module_query to the on-screen chapter
    # title (usually English) rather than what the user actually typed/
    # said, so that fallback silently ignores a Hindi request.
    message: str | None = None


def _flatten_modules(contents: dict) -> list[dict]:
    return contents.get("modules") or contents.get("chapters") or []


def _module_text(module: dict) -> str:
    parts = [module.get("title", "")]
    description = module.get("description") or module.get("summary")
    if description:
        parts.append(description)
    lessons = module.get("chapters", module.get("lessons", []))
    for lesson in lessons:
        title = lesson.get("title")
        if title:
            parts.append(f"- {title}")
    return "\n".join(p for p in parts if p)


def _find_module(modules: list[dict], module_query: str) -> dict | None:
    m = re.search(r"module\s*(\d+)", module_query, re.IGNORECASE)
    if m:
        idx = int(m.group(1)) - 1  # "module 1" -> modules[0]
        if 0 <= idx < len(modules):
            return modules[idx]

    query_lower = module_query.lower().strip()
    for module in modules:
        title = (module.get("title") or "").lower()
        if title and (query_lower in title or title in query_lower):
            return module
    return None


@router.post("/read")
@limiter.limit("20/minute")
async def read_module(request: Request, payload: ModuleReadRequest):
    contents = fetch_course_contents(payload.course_slug)
    if not contents:
        raise HTTPException(404, f"Course '{payload.course_slug}' not found or has no contents.")

    modules = _flatten_modules(contents)
    if not modules:
        raise HTTPException(404, f"No modules found for course '{payload.course_slug}'.")

    module = _find_module(modules, payload.module_query)
    if not module:
        raise HTTPException(404, f"No module matching '{payload.module_query}'.")

    text = _module_text(module)
    language = resolve_language(payload.language, payload.message or payload.module_query)
    if language != "en":
        text = translate(text, language)

    return {
        "module_title": module.get("title", "Module"),
        "transcript": text,
        "language": language,
        # Spoken client-side via the browser's Web Speech API (see
        # embed.js/speakText) instead of server-side TTS - that audio was
        # going unused and its timeouts were adding dead latency here.
        "audio_base64": None,
        "audio_mime": None,
    }
