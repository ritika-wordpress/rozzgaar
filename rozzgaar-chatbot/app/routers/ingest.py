import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.limiter import limiter
from app.models.schemas import IngestResponse
from app.services.knowledge_base import kb

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/refresh", response_model=IngestResponse)
@limiter.limit("5/hour")
def refresh(request: Request, x_admin_secret: str = Header(...)) -> IngestResponse:
    if not secrets.compare_digest(x_admin_secret, settings.admin_secret):
        raise HTTPException(status_code=401, detail="Invalid admin secret.")
    stats = kb.build()
    return IngestResponse(**stats)
