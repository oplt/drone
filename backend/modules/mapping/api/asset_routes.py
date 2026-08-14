from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.mapping.api.mapping_route_schemas import MappingSignedUrlOut
from backend.modules.mapping.api.mapping_route_support import (
    asset_gateway,
    get_owned_asset_or_404,
)
from backend.modules.mapping.application import mapping_application

router = APIRouter(tags=["mapping"])


@router.get("/assets/{asset_id}/signed-url", response_model=MappingSignedUrlOut)
async def get_mapping_asset_signed_url(
    asset_id: int,
    request: Request,
    ttl_seconds: int = Query(default=900, ge=60, le=86400),
    path: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> MappingSignedUrlOut:
    clean_path = path.strip().lstrip("/")
    if ".." in Path(clean_path).parts:
        raise HTTPException(status_code=400, detail="Invalid asset sub-path")

    asset, owner_id = await get_owned_asset_or_404(db, asset_id=asset_id, user=org_user.user)
    gateway = asset_gateway()
    relative_url, exp = gateway.build_signed_url(
        asset_id=asset.id,
        user_id=owner_id,
        ttl_seconds=ttl_seconds,
        path=clean_path,
    )
    absolute_url = (
        await gateway.build_download_url(
            asset_id=asset.id,
            user_id=owner_id,
            org_id=org_user.org_id,
            asset_url=asset.url,
            asset_type=asset.type,
            ttl_seconds=ttl_seconds,
            path=clean_path,
        )
        if settings.storage_backend == "s3"
        else f"{str(request.base_url).rstrip('/')}{relative_url}"
    )
    return MappingSignedUrlOut(
        asset_id=asset.id,
        asset_type=asset.type,
        expires_at=datetime.fromtimestamp(exp, tz=UTC),
        relative_url=relative_url if settings.storage_backend != "s3" else "",
        url=absolute_url,
        path=clean_path or None,
    )


@router.get("/assets/{asset_id}/download")
async def download_mapping_asset(
    asset_id: int,
    exp: int = Query(...),
    sig: str = Query(...),
    path: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    clean_path = path.strip().lstrip("/")
    if ".." in Path(clean_path).parts:
        raise HTTPException(status_code=400, detail="Invalid asset sub-path")

    pair = await mapping_application.get_asset_record(db, asset_id=asset_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset, owner_id, org_id = pair
    owner_id = int(owner_id)
    gateway = asset_gateway()
    if not gateway.verify(
        asset_id=asset_id,
        user_id=owner_id,
        exp=exp,
        sig=sig,
        path=clean_path,
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired asset token")

    local_target = gateway.resolve_local_target(
        asset_url=asset.url,
        asset_type=asset.type,
        path=clean_path,
    )
    headers = {"Cache-Control": "private, max-age=300"}
    if local_target:
        return FileResponse(str(local_target), headers=headers)

    if asset.url.startswith("http://") or asset.url.startswith("https://"):
        remote = asset.url.rstrip("/")
        if clean_path:
            remote = f"{remote}/{clean_path}"
        return RedirectResponse(remote, status_code=307, headers=headers)

    if settings.storage_backend == "s3":
        remote = await gateway.build_download_url(
            asset_id=asset.id,
            user_id=owner_id,
            org_id=int(org_id) if org_id is not None else None,
            asset_url=asset.url,
            asset_type=asset.type,
            ttl_seconds=max(60, exp - int(datetime.now(UTC).timestamp())),
            path=clean_path,
        )
        return RedirectResponse(remote, status_code=307, headers=headers)

    raise HTTPException(status_code=404, detail="Asset content not available")
