# backend/config_runtime.py
from __future__ import annotations
from typing import Any, Dict

from backend.config import Settings as EnvSettings
from backend.db.repository import SettingsRepository  # the repo you create for Settings table

_env = EnvSettings()  # env bootstrap (still ok)

async def get_runtime_settings(repo: SettingsRepository) -> EnvSettings:
    db_values: Dict[str, Any] = await repo.get_settings()  # dict from DB
    merged = _env.model_dump()
    merged.update(db_values)  # DB overrides env
    return EnvSettings.model_validate(merged)
