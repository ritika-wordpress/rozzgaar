"""Turns a lecture video URL into a text transcript, so "summarize this
video" can reuse the exact same llm.summarize() used for text content.

Pipeline: download (size-capped, host-allowlisted) -> extract+compress
audio with ffmpeg -> transcribe with Groq Whisper (app.services.stt),
splitting into chunks first if the compressed audio would still be too
big for one Whisper call. Every step is cached to disk keyed by the
video URL, since a lecture video's content never changes and re-running
this pipeline is the single most expensive thing this backend does
(bandwidth + wall-clock + Whisper API cost) - the cache is what makes a
second person (or the same person clicking "Summary" twice) essentially
free.
"""
import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import HTTPException

from app.config import settings
from app.services.stt import transcribe_audio

logger = logging.getLogger(__name__)

# Generous cap on the *downloaded* video itself - a single lecture video,
# not the whole course. Keeps one request from tying up disk/bandwidth
# indefinitely on a misconfigured or huge file.
_MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500MB
_DOWNLOAD_CHUNK = 1024 * 1024  # 1MB

# Groq's Whisper endpoint caps request size (25MB on the free tier) - stay
# comfortably under that after compression, and split into chunks if the
# compressed audio is still bigger than this.
_MAX_WHISPER_AUDIO_BYTES = 20 * 1024 * 1024  # 20MB
_CHUNK_SECONDS = 600  # 10-minute audio segments when splitting is needed

# Compressed-audio target: mono, 16kHz, 48kbps - more than enough for
# speech-to-text accuracy, and small enough that even a ~45min lecture
# usually clears _MAX_WHISPER_AUDIO_BYTES without needing to be split.
_AUDIO_CODEC_ARGS = ["-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k"]

_CACHE_LOCK = threading.Lock()


def _cache_path() -> Path:
    p = Path(settings.data_dir) / "video_transcripts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(video_url: str) -> str:
    return hashlib.sha256(video_url.strip().encode("utf-8")).hexdigest()


def _load_cache() -> dict:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Video-transcript cache unreadable (%s), starting fresh.", exc)
        return {}


def _save_cache_entry(video_url: str, transcript: str) -> None:
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[_cache_key(video_url)] = {"video_url": video_url, "transcript": transcript}
        try:
            _cache_path().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to persist video-transcript cache: %s", exc)


def get_cached_transcript(video_url: str) -> str | None:
    entry = _load_cache().get(_cache_key(video_url))
    return entry.get("transcript") if entry else None


def _assert_allowed_host(video_url: str) -> None:
    host = (urlparse(video_url).hostname or "").lower()
    if not host:
        raise HTTPException(status_code=400, detail="video_url is not a valid absolute URL.")
    allowed = settings.allowed_video_domain_list
    if not any(host == d or host.endswith("." + d) for d in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"video_url host '{host}' is not allow-listed. "
                   f"Set ALLOWED_VIDEO_DOMAINS in .env to include it if this is expected.",
        )


def _download_video(video_url: str, dest: Path) -> None:
    try:
        with requests.get(video_url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=_DOWNLOAD_CHUNK):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > _MAX_VIDEO_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Video exceeds the {_MAX_VIDEO_BYTES // (1024 * 1024)}MB limit for automatic summarization.",
                        )
                    f.write(chunk)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not download video: {exc}") from exc


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise HTTPException(
            status_code=500,
            detail="ffmpeg is not installed on the server - required to extract audio from video for transcription.",
        )
    cmd = ["ffmpeg", "-y", "-i", str(video_path), *_AUDIO_CODEC_ARGS, str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not audio_path.exists():
        logger.warning("ffmpeg audio extraction failed: %s", result.stderr[-2000:])
        raise HTTPException(status_code=502, detail="Could not extract audio from the video file.")


def _probe_duration_seconds(path: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def _split_audio(audio_path: Path, out_dir: Path) -> list[Path]:
    """Splits into fixed-length segments (ffmpeg's own segment muxer -
    stream-copy, no re-encode) so a long lecture's audio still fits under
    Whisper's per-request size cap. Returns segment paths in order."""
    pattern = out_dir / "chunk_%03d.mp3"
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-f", "segment", "-segment_time", str(_CHUNK_SECONDS), "-c", "copy",
        str(pattern),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.warning("ffmpeg audio splitting failed: %s", result.stderr[-2000:])
        raise HTTPException(status_code=502, detail="Could not split long audio for transcription.")
    return sorted(out_dir.glob("chunk_*.mp3"))


def _transcribe_file(path: Path, language_hint: str | None) -> str:
    data = path.read_bytes()
    return transcribe_audio(data, filename=path.name, language_hint=language_hint)


def build_video_transcript(video_url: str, language_hint: str | None = None) -> str:
    """Downloads + transcribes a lecture video (see module docstring for
    the full pipeline). Always transcribes in the video's own spoken
    language (language_hint is a Whisper accuracy hint, e.g. 'en'/'hi' -
    NOT a translation target); translate the resulting text afterwards
    with llm.translate()/llm.summarize() the same way any other page
    text is, so this function stays reusable regardless of what language
    the user wants the eventual summary in."""
    _assert_allowed_host(video_url)

    with tempfile.TemporaryDirectory(prefix="rzg-video-") as tmp:
        tmp_dir = Path(tmp)
        video_path = tmp_dir / "source_video"
        audio_path = tmp_dir / "audio.mp3"

        _download_video(video_url, video_path)
        _extract_audio(video_path, audio_path)

        if audio_path.stat().st_size <= _MAX_WHISPER_AUDIO_BYTES:
            transcript = _transcribe_file(audio_path, language_hint)
        else:
            chunks_dir = tmp_dir / "chunks"
            chunks_dir.mkdir()
            segments = _split_audio(audio_path, chunks_dir)
            if not segments:
                raise HTTPException(status_code=502, detail="Audio splitting produced no segments.")
            # Sequential, not parallel: keeps memory/API concurrency bounded
            # for what's already a rate-limited, heavyweight endpoint.
            transcript = " ".join(_transcribe_file(seg, language_hint) for seg in segments).strip()

    if not transcript or not transcript.strip():
        raise HTTPException(status_code=502, detail="Transcription produced no text - the video may have no speech.")

    _save_cache_entry(video_url, transcript)
    return transcript


def get_or_build_transcript(video_url: str, language_hint: str | None = None) -> tuple[str, bool]:
    """Returns (transcript, was_cached)."""
    cached = get_cached_transcript(video_url)
    if cached:
        return cached, True
    return build_video_transcript(video_url, language_hint), False
