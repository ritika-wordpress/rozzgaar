from fastapi import APIRouter, HTTPException, Request

from app.limiter import limiter
from app.models.schemas import SummarizeRequest, SummarizeResponse, VideoSummarizeRequest, VideoSummarizeResponse
from app.services import llm
from app.services.intent import extract_summary_word_count
from app.services.knowledge_base import kb
from app.services.language import resolve_language
from app.services.text_clean import strip_decorative_symbols
from app.services.video_transcript import get_or_build_transcript

router = APIRouter(prefix="/summarize", tags=["summarize"])


@router.post("/", response_model=SummarizeResponse)
@limiter.limit("20/minute")
def summarize(request: Request, payload: SummarizeRequest) -> SummarizeResponse:
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
    text = strip_decorative_symbols(text)

    language = resolve_language(payload.language, payload.message or text[:500])
    word_count = payload.word_count
    if word_count is None and payload.message:
        word_count = extract_summary_word_count(payload.message)
    summary = llm.summarize(text, payload.length, language, title=title, word_count=word_count)

    return SummarizeResponse(summary=summary, length=payload.length, language=language, source_title=title)


@router.post("/video", response_model=VideoSummarizeResponse)
@limiter.limit("5/minute")
def summarize_video(request: Request, payload: VideoSummarizeRequest) -> VideoSummarizeResponse:
    """Summarizes a lecture video: downloads it, transcribes it with
    Whisper (cached on disk per video_url so repeat requests - by anyone,
    not just the same visitor - are near-instant), then runs the exact
    same summarize() used for text content. `language` controls the
    SUMMARY's language, same convention as /summarize/ - it has nothing
    to do with the language spoken in the video itself, which Whisper
    auto-detects on its own.
    """
    video_url = (payload.video_url or "").strip()
    if not video_url:
        raise HTTPException(status_code=400, detail="video_url is required.")

    transcript, was_cached = get_or_build_transcript(video_url)
    transcript = strip_decorative_symbols(transcript)

    language = resolve_language(payload.language, payload.message or payload.module_title or "")
    word_count = payload.word_count
    if word_count is None and payload.message:
        word_count = extract_summary_word_count(payload.message)

    summary = llm.summarize(transcript, payload.length, language, title=payload.module_title, word_count=word_count)

    return VideoSummarizeResponse(
        summary=summary,
        length=payload.length,
        language=language,
        source_title=payload.module_title,
        transcript_cached=was_cached,
    )