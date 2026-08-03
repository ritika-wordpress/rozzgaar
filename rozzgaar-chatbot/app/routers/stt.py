from fastapi import APIRouter, File, Form, UploadFile

from app.models.schemas import STTResponse
from app.services.language import detect_language
from app.services.stt import transcribe_audio

router = APIRouter(prefix="/stt", tags=["stt"])


@router.post("/transcribe", response_model=STTResponse)
async def transcribe(audio: UploadFile = File(...), language_hint: str | None = Form(None)) -> STTResponse:
    """Upload a recorded voice clip (webm/mp3/wav/m4a) and get back the
    transcript. `language_hint` is optional ('en' or 'hi') - leave blank to
    auto-detect. Use this if you want the transcript only (e.g. to show it
    in a text box); use /voice/chat if you want a full spoken reply too."""
    data = await audio.read()
    transcript = transcribe_audio(data, filename=audio.filename or "audio.webm", language_hint=language_hint)
    language = detect_language(transcript)
    return STTResponse(transcript=transcript, language=language)
