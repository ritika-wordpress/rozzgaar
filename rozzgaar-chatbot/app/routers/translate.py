from fastapi import APIRouter, HTTPException, Request

from app.limiter import limiter
from app.models.schemas import TranslateBatchRequest, TranslateBatchResponse
from app.services import llm
from app.services.language import resolve_language

router = APIRouter(prefix="/translate", tags=["translate"])

# A real "translate this page" walk can easily produce a few hundred text
# nodes on a content-heavy page, but an unbounded array is still a way to
# force a huge number of translate requests off one request - cap both
# dimensions the same way chat.py caps live page_content.
_MAX_ITEMS = 600
_MAX_TOTAL_CHARS = 60000


@router.post("/batch", response_model=TranslateBatchResponse)
@limiter.limit("15/minute")
def translate_batch(request: Request, payload: TranslateBatchRequest) -> TranslateBatchResponse:
    texts = payload.texts
    if not texts:
        raise HTTPException(status_code=400, detail="Provide at least one string in texts.")
    if len(texts) > _MAX_ITEMS:
        raise HTTPException(status_code=400, detail=f"Too many items ({len(texts)}); max is {_MAX_ITEMS}. "
                                                      "Split the page walk into smaller batched requests.")
    if sum(len(t) for t in texts) > _MAX_TOTAL_CHARS:
        raise HTTPException(status_code=400, detail=f"Combined text too long; max is {_MAX_TOTAL_CHARS} characters "
                                                      "per batch. Split the page walk into smaller batched requests.")

    # "auto" has no real page-wide message to detect from here (this is a
    # DOM walk, not chat) - resolve_language("auto", "") falls through to
    # detect_language's empty-text case and returns "en", which matches
    # what the langGate buttons actually send (always an explicit hi/en).
    language = resolve_language(payload.language, payload.message or "")
    # llm.translate_batch fails open per-item now (Google Translate via
    # deep-translator, not an LLM): a node that can't be translated - rate
    # limited, network hiccup, whatever - comes back as its own original
    # text rather than raising, so this call itself won't 500/503. The page
    # stays usable even if only some nodes end up translated.
    translated = llm.translate_batch(tuple(texts), language)
    return TranslateBatchResponse(texts=translated, language=language)
