from fastapi import HTTPException, UploadFile

# Voice clips from the widget are short (a few seconds of speech), so 10MB
# is generous headroom while still capping worst-case memory use per
# request - reading in chunks means we reject oversized uploads without
# ever buffering the full thing in memory first.
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB
_CHUNK_SIZE = 1024 * 1024  # 1MB per read


async def read_capped(upload: UploadFile, max_bytes: int = MAX_AUDIO_BYTES) -> bytes:
    """Read an UploadFile's contents, aborting with 413 if it exceeds
    max_bytes - without ever holding more than max_bytes + one chunk in
    memory at once."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large (max {max_bytes // (1024 * 1024)}MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)
