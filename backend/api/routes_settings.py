from __future__ import annotations
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.db.repository import SettingsRepository
from backend.auth.deps import require_admin
from backend.utils.config_runtime import get_runtime_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPayload(BaseModel):
    data: Dict[str, Any]


@router.get("", response_model=Dict[str, Any])
async def get_settings(
    repo: SettingsRepository = Depends(SettingsRepository),
    user=Depends(require_admin),
):
    return await repo.get_settings()


@router.put("", response_model=Dict[str, Any])
async def save_settings(
    payload: SettingsPayload,
    repo: SettingsRepository = Depends(SettingsRepository),
    user=Depends(require_admin),
):
    await repo.upsert_settings(payload.data)
    # Refresh runtime settings so changes take effect immediately.
    await get_runtime_settings(repo)
    return payload.data
