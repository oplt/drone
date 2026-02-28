from __future__ import annotations

from fastapi import APIRouter, Request
from backend.schemas.settings import SettingsDoc
from backend.utils.config_runtime import get_runtime_settings
from backend.db.repository import SettingsRepository

router = APIRouter(prefix="/api/settings", tags=["settings"])

svc = SettingsRepository()


@router.get("", response_model=SettingsDoc)
async def get_settings():
    return await svc.get_settings_doc()


@router.put("", response_model=SettingsDoc)
async def put_settings(payload: SettingsDoc, request: Request):
    saved = await svc.put_settings_doc(payload.model_dump())

    # refresh runtime settings used by orchestrator/preflight (loaded on startup) :contentReference[oaicite:9]{index=9}
    request.app.state.settings = await get_runtime_settings(SettingsRepository())

    return saved