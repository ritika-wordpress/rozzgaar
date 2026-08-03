from fastapi import APIRouter, HTTPException

from app.models.schemas import SummarizeRequest, SummarizeResponse
from app.services import llm
from app.services.intent import extract_summary_word_count
from app.services.knowledge_base import kb
from app.services.language import resolve_language

router = APIRouter(prefix="/summarize", tags=["summarize"])


@router.post("/", response_model=SummarizeResponse)
def summarize(payload: SummarizeRequest) -> SummarizeResponse:
    slug = payload.course_slug or payload.bundle_slug
    title = None
    text = payload.text

    if slug:
        doc = kb.get_full_doc(slug)
        if not doc:
            raise HTTPException(status_code=404, detail=f"No indexed content found for slug '{slug}'. "
                                                          f"Run /ingest/refresh first, or check the slug.")
        text = doc.text
        title = doc.title

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Provide either course_slug, bundle_slug, or text.")

    language = resolve_language(payload.language, payload.message or text[:500])
    word_count = payload.word_count
    if word_count is None and payload.message:
        word_count = extract_summary_word_count(payload.message)
    summary = llm.summarize(text, payload.length, language, title=title, word_count=word_count)

    return SummarizeResponse(summary=summary, length=payload.length, language=language, source_title=title)
