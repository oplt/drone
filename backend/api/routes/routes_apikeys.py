from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.auth.deps import OrgUser, require_org_user
from backend.db.models import ApiKey
from backend.db.session import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = []
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list
    created_at: datetime
    expires_at: datetime | None
    revoked: bool
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyOut):
    raw_key: str  # only returned once on creation


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(org_user: OrgUser = Depends(require_org_user)):
    """List all API keys for the authenticated user's org. Never exposes key_hash."""
    async with Session() as db:
        q = await db.execute(
            select(ApiKey).where(
                ApiKey.org_id == org_user.org_id,
                ApiKey.revoked == False,  # noqa: E712
            ).order_by(ApiKey.created_at.desc())
        )
        keys = q.scalars().all()
        return [ApiKeyOut.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    org_user: OrgUser = Depends(require_org_user),
):
    """
    Create a new API key for the org. The raw key is returned exactly once —
    it cannot be recovered after this response.

    Key format: sk-{8-hex-prefix}_{32-hex-secret}
    Only the SHA-256 of the secret is stored.
    """
    if org_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no associated organisation")

    prefix = secrets.token_hex(4)   # 8 hex chars
    secret = secrets.token_hex(16)  # 32 hex chars
    raw_key = f"sk-{prefix}_{secret}"
    key_hash = hashlib.sha256(secret.encode()).hexdigest()

    async with Session() as db:
        api_key = ApiKey(
            org_id=org_user.org_id,
            name=body.name,
            key_prefix=prefix,
            key_hash=key_hash,
            scopes=body.scopes,
            expires_at=body.expires_at,
            created_by_user_id=org_user.user.id,
        )
        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

    logger.info(
        "API key created",
        extra={
            "org_id": org_user.org_id,
            "user_id": org_user.user.id,
            "key_prefix": prefix,
            "key_name": body.name,
        },
    )

    out = ApiKeyOut.model_validate(api_key)
    return ApiKeyCreated(**out.model_dump(), raw_key=raw_key)


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: int,
    org_user: OrgUser = Depends(require_org_user),
):
    """Revoke an API key. The key is soft-deleted (revoked=True)."""
    async with Session() as db:
        q = await db.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.org_id == org_user.org_id,
            )
        )
        api_key = q.scalar_one_or_none()
        if api_key is None:
            raise HTTPException(status_code=404, detail="API key not found")

        api_key.revoked = True
        await db.commit()

    logger.info(
        "API key revoked",
        extra={
            "org_id": org_user.org_id,
            "user_id": org_user.user.id,
            "key_id": key_id,
        },
    )
