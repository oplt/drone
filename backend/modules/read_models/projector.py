"""Redis read models updated from mission/alert/job domain events."""

from __future__ import annotations

import json
from typing import Any

from backend.infrastructure.cache.redis import get_redis_client


class ReadModelProjector:
    """Idempotent projections; source-of-truth remains PostgreSQL."""

    async def _write(self, key: str, payload: dict[str, Any], *, ttl: int = 86_400) -> None:
        redis = get_redis_client()
        if redis is None:
            return
        await redis.set(key, json.dumps(payload, default=str), ex=ttl)

    async def project_mission(
        self, *, org_id: int, flight_id: int | str, payload: dict[str, Any]
    ) -> None:
        await self._write(f"read-model:mission:{org_id}:{flight_id}", payload)

    async def project_alert(
        self, *, org_id: int, alert_id: int | str, payload: dict[str, Any]
    ) -> None:
        await self._write(f"read-model:alert:{org_id}:{alert_id}", payload)

    async def project_job(self, *, org_id: int, job_id: int | str, payload: dict[str, Any]) -> None:
        await self._write(f"read-model:job:{org_id}:{job_id}", payload, ttl=7_200)


read_model_projector = ReadModelProjector()
