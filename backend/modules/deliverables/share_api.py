"""Public share-link endpoint for FieldDeliverables.

No authentication — these are intentionally unauthenticated public links
controlled via share_token and optional expires_at.

Prefix  : (none — mounted at root as /share/{token})
Tags    : ["deliverables"]
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.modules.deliverables.models import FieldDeliverable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/share", tags=["deliverables"])

_CONTENT_TYPE_MAP: dict[str, str] = {
    "GEOJSON": "application/geo+json",
    "KML": "application/vnd.google-earth.kml+xml",
    "HTML_SUMMARY": "text/html",
    "QA_CHECKLIST": "application/json",
}


@router.get("/{token}")
async def get_deliverable_share(token: str):
    """Serve a shared field deliverable by its share token.

    - Returns 404 if the token is unknown or the deliverable is not yet ready.
    - Returns 410 if the share link has expired.
    - For S3 storage: issues a redirect to a short-lived presigned URL.
    - For local storage: serves the file content directly.
    """
    async with Session() as db:
        q = await db.execute(select(FieldDeliverable).where(FieldDeliverable.share_token == token))
        d = q.scalar_one_or_none()

        if not d or d.status != "ready":
            raise HTTPException(status_code=404, detail="Deliverable not found or not ready")

        if d.expires_at and d.expires_at < datetime.now(UTC):
            raise HTTPException(status_code=410, detail="Share link expired")

        if settings.storage_backend == "s3":
            from backend.infrastructure.storage import ObjectStorageClient

            try:
                client = ObjectStorageClient()
                url = await client.generate_presigned_url(d.url, expires_in=3600)
                return RedirectResponse(url=url, status_code=302)
            except Exception:
                logger.exception("Failed to generate presigned URL for deliverable %s", d.id)
                raise HTTPException(
                    status_code=500, detail="Could not generate download URL"
                ) from None

        else:
            # Local storage — serve the file directly
            from pathlib import Path

            path = Path(d.url)
            if not path.exists():
                logger.error("Deliverable %s has status=ready but file missing at %s", d.id, path)
                raise HTTPException(status_code=404, detail="File not found")

            content_type = _CONTENT_TYPE_MAP.get(d.type, "application/octet-stream")
            try:
                async with aiofiles.open(path, "rb") as f:
                    content = await f.read()
            except OSError:
                logger.exception("Failed to read deliverable file %s", path)
                raise HTTPException(status_code=500, detail="Could not read file") from None

            return Response(content=content, media_type=content_type)
