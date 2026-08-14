from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends

from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import require_user
from backend.modules.identity.models import User

runtime_router = APIRouter(prefix="/runtime", tags=["runtime"])


@runtime_router.get("/status")
async def get_runtime_status(user: User = Depends(require_user)) -> dict[str, Any]:
    telemetry = telemetry_manager.runtime_snapshot()
    return {
        "telemetry": telemetry,
        "timestamp": time.time(),
    }
