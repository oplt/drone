from __future__ import annotations
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.db.repository import SettingsRepository

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPayload(BaseModel):
    data: Dict[str, Any]


@router.get("", response_model=Dict[str, Any])
async def get_settings(
    repo: SettingsRepository = Depends(SettingsRepository),
    # user=Depends(require_user),  # <-- plug in your auth dependency
):
    return await repo.get_settings()


@router.put("", response_model=Dict[str, Any])
async def save_settings(
    payload: SettingsPayload,
    repo: SettingsRepository = Depends(SettingsRepository),
    # user=Depends(require_user),  # <-- plug in your auth dependency
):
    await repo.upsert_settings(payload.data)
    return payload.data
