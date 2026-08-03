import asyncio
import io
import logging

import edge_tts
from gtts import gTTS

from app.config import settings

logger = logging.getLogger(__name__)

_VOICE_BY_LANG = {
    "hi": settings.tts_voice_hi,   # e.g. hi-IN-SwaraNeural
    "en": settings.tts_voice_en,   # e.g. en-IN-NeerjaNeural
}

# gTTS lang codes and a tld chosen for an Indian accent where available -
# used only as a fallback when edge-tts (our primary, better-quality voice)
# fails outright, so callers still get *some* audio instead of silence.
_GTTS_LANG_BY_LANG = {"hi": "hi", "en": "en"}
_GTTS_TLD = "co.in"
GTTS_TIMEOUT_SECONDS = 12

# Microsoft's edge-tts endpoint has been known to hang instead of failing
# fast (see edge-tts GitHub issues #290/#401/#458) - without a timeout,
# a stalled connection here blocks the whole /voice/chat request forever
# and the browser is left showing "transcribing..." indefinitely.
TTS_TIMEOUT_SECONDS = 12


# A cancelled edge-tts attempt (e.g. one that just timed out) can leave its
# internal connection state such that the *next* call on the same process
# returns HTTP 200-equivalent success but with truncated/empty audio - no
# exception raised, so timeout/exception handling alone won't catch it.
# A real spoken sentence is always well over this many bytes of MP3; treat
# anything smaller as a failed attempt rather than trusting it blindly.
_MIN_PLAUSIBLE_AUDIO_BYTES = 2000


def _looks_like_valid_mp3(data: bytes | None) -> bool:
    return bool(data) and len(data) >= _MIN_PLAUSIBLE_AUDIO_BYTES


def pick_voice(language: str, override: str | None = None) -> str:
    if override:
        return override
    return _VOICE_BY_LANG.get(language, _VOICE_BY_LANG["en"])


async def _stream_speech(text: str, selected_voice: str) -> bytes:
    communicator = edge_tts.Communicate(text, selected_voice)
    buffer = io.BytesIO()
    async for chunk in communicator.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


def _gtts_sync(text: str, language: str) -> bytes:
    """Blocking gTTS call - runs in a worker thread via asyncio.to_thread
    since gTTS itself is synchronous (uses `requests` under the hood)."""
    lang = _GTTS_LANG_BY_LANG.get(language, "en")
    buffer = io.BytesIO()
    gTTS(text=text, lang=lang, tld=_GTTS_TLD).write_to_fp(buffer)
    return buffer.getvalue()


async def _gtts_fallback(text: str, language: str) -> bytes | None:
    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(_gtts_sync, text, language), timeout=GTTS_TIMEOUT_SECONDS
        )
        if not _looks_like_valid_mp3(data):
            logger.warning("gTTS returned suspiciously small output (%d bytes) for language=%s",
                            len(data) if data else 0, language)
            return None
        return data
    except Exception:
        logger.exception("gTTS fallback also failed for language=%s", language)
        return None


async def synthesize_speech(text: str, language: str, voice: str | None = None) -> bytes | None:
    """Returns MP3 audio bytes for the given text. Tries Microsoft Edge TTS
    first (free, no API key, better voice quality) - picks a Hindi or
    English neural voice automatically based on `language`, or uses `voice`
    if explicitly given (e.g. 'hi-IN-MadhurNeural', 'en-US-AriaNeural').
    Retries once on timeout, since the free endpoint is often just
    intermittently slow rather than truly hung.

    Every result (including a "successful" one) is size-checked before
    being trusted - a cancelled prior attempt can leave edge-tts returning
    truncated audio with no exception at all, so a clean return isn't proof
    the bytes are actually playable.

    If edge-tts fails both attempts (or returns bad audio both times),
    falls back to gTTS (also free, lower voice quality but a different
    provider/network path) rather than returning no audio at all. Only
    returns None if both providers fail, so callers can fall back to a
    text-only reply rather than 500ing."""
    selected_voice = pick_voice(language, voice)
    for attempt in (1, 2):
        try:
            data = await asyncio.wait_for(
                _stream_speech(text, selected_voice), timeout=TTS_TIMEOUT_SECONDS
            )
            if _looks_like_valid_mp3(data):
                return data
            logger.warning("edge-tts returned suspiciously small output (%d bytes) for voice=%s "
                            "(attempt %d/2) - treating as a failed attempt",
                            len(data) if data else 0, selected_voice, attempt)
        except asyncio.TimeoutError:
            logger.warning("TTS timed out after %ss for voice=%s (attempt %d/2)",
                            TTS_TIMEOUT_SECONDS, selected_voice, attempt)
        except Exception:
            logger.exception("TTS failed for voice=%s (attempt %d/2)", selected_voice, attempt)

    logger.info("Falling back to gTTS for language=%s after edge-tts failed twice", language)
    return await _gtts_fallback(text, language)