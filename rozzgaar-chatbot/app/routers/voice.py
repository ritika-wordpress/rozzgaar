from fastapi import APIRouter, File, Form, Request, UploadFile

from app.limiter import limiter
from app.models.schemas import VoiceChatResponse
from app.routers.chat import build_chat_response
from app.services.stt import transcribe_audio
from app.services.uploads import read_capped

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/chat", response_model=VoiceChatResponse)
@limiter.limit("10/minute")
async def voice_chat(
    request: Request,
    audio: UploadFile = File(...),
    page_url: str | None = Form(None),
    page_content: str | None = Form(None),
    language: str | None = Form("auto"),
) -> VoiceChatResponse:
    """One-call voice round trip: upload a recorded question (webm/mp3/wav/m4a),
    get back the transcript and a grounded text reply. The reply is spoken
    client-side via the browser's Web Speech API (see embed.js/speakText) -
    this endpoint no longer calls the server-side TTS provider, since that
    audio was going unused and its edge-tts/gTTS timeouts were adding
    ~24s of dead latency to every request for nothing.

    page_url/page_content are optional, same meaning as on the text /chat/
    endpoint - send them so "read this page" works by voice too."""
    raw_audio = await read_capped(audio)
    transcript = transcribe_audio(raw_audio, filename=audio.filename or "audio.webm")

    chat_result = build_chat_response(transcript, requested_language=language or "auto",
                                       page_url=page_url, page_content=page_content)

    return VoiceChatResponse(
        transcript=transcript,
        reply=chat_result.reply,
        language=chat_result.language,
        sources=chat_result.sources,
        suggested_questions=chat_result.suggested_questions,
        audio_base64=None,
    )