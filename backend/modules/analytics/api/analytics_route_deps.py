from __future__ import annotations

from backend.infrastructure.cache.redis import get_redis_client

VALID_TELEMETRY_SUMMARY_RESOLUTIONS = {1, 10, 60}

__all__ = ["VALID_TELEMETRY_SUMMARY_RESOLUTIONS", "get_redis_client"]
