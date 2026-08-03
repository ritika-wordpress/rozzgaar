from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models.schemas import TTSRequest
from app.services.language import resolve_language
from app.services.tts import synthesize_speech

router = APIRouter(prefix="/tts", tags=["tts"])


@router.post("/speak")
async def speak(payload: TTSRequest) -> Response:
    language = resolve_language(payload.language, payload.text)
    audio_bytes = await synthesize_speech(payload.text, language, voice=payload.voice)
    if audio_bytes is None:
        # synthesize_speech() returns None (instead of raising) on timeout
        # or any TTS-side failure - surface that as a normal HTTP error so
        # the frontend's res.ok check handles it instead of getting a
        # broken/empty audio response.
        raise HTTPException(status_code=502, detail="Text-to-speech is temporarily unavailable.")
    return Response(content=audio_bytes, media_type="audio/mpeg")