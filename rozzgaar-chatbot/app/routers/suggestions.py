from fastapi import APIRouter, HTTPException, Request

from app.limiter import limiter
from app.models.schemas import QAItem, SuggestQuestionsRequest, SuggestQuestionsResponse
from app.services import llm
from app.services.knowledge_base import kb
from app.services.language import resolve_language

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.post("/", response_model=SuggestQuestionsResponse)
@limiter.limit("20/minute")
def suggest_questions(request: Request, payload: SuggestQuestionsRequest) -> SuggestQuestionsResponse:
    context_text = None
    if payload.text and payload.text.strip():
        # Raw text (e.g. text scraped live from the page by the widget) is
        # used as-is, same convention as /summarize/'s `text` field - no
        # point running it back through TF-IDF retrieval against itself.
        context_text = payload.text
    elif payload.course_slug:
        doc = kb.get_full_doc(payload.course_slug)
        if not doc:
            raise HTTPException(status_code=404, detail=f"No indexed content for slug '{payload.course_slug}'.")
        context_text = doc.text
    elif payload.topic:
        chunks = kb.retrieve(payload.topic, top_k=5)
        context_text = "\n".join(c.text for c in chunks) or payload.topic
    else:
        raise HTTPException(status_code=400, detail="Provide text, course_slug, or topic.")

    language = resolve_language(payload.language, context_text[:500])
    qa = llm.generate_suggested_questions(context_text, language, count=payload.count)

    return SuggestQuestionsResponse(
        questions=[QAItem(**item) for item in qa],
        language=language,
    )
