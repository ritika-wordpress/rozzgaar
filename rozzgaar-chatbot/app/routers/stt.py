from fastapi import APIRouter, File, Form, Request, UploadFile

from app.limiter import limiter
from app.models.schemas import STTResponse
from app.services.language import detect_language
from app.services.stt import transcribe_audio
from app.services.uploads import read_capped

router = APIRouter(prefix="/stt", tags=["stt"])


@router.post("/transcribe", response_model=STTResponse)
@limiter.limit("10/minute")
async def transcribe(request: Request, audio: UploadFile = File(...), language_hint: str | None = Form(None)) -> STTResponse:
    """Upload a recorded voice clip (webm/mp3/wav/m4a) and get back the
    transcript. `language_hint` is optional ('en' or 'hi') - leave blank to
    auto-detect. Use this if you want the transcript only (e.g. to show it
    in a text box); use /voice/chat if you want a full spoken reply too."""
    data = await read_capped(audio)
    transcript = transcribe_audio(data, filename=audio.filename or "audio.webm", language_hint=language_hint)
    language = detect_language(transcript)
    return STTResponse(transcript=transcript, language=language)
