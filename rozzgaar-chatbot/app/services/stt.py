import logging

from groq import Groq

from app.config import settings

logger = logging.getLogger(__name__)

_client = Groq(api_key=settings.groq_api_key)


def transcribe_audio(file_bytes: bytes, filename: str = "audio.webm", language_hint: str | None = None) -> str:
    """Transcribes recorded speech (webm/mp3/wav/m4a - anything ffmpeg reads)
    to text using Groq's hosted Whisper. Works for both Hindi and English
    speech; leave language_hint=None to let Whisper auto-detect, or pass
    'hi'/'en' if you already know it (slightly faster + more accurate).
    """
    result = _client.audio.transcriptions.create(
        file=(filename, file_bytes),
        model=settings.groq_stt_model,
        language=language_hint,
        response_format="text",
    )
    # SDK returns a plain string when response_format="text"
    text = result if isinstance(result, str) else getattr(result, "text", "")
    return text.strip()
