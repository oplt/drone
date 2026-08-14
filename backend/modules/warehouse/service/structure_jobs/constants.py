"""Structure job constants and shared caches."""

from __future__ import annotations

import logging
from typing import Any

from backend.infrastructure.cache.local import BoundedTTLCache

STRUCTURE_EXTRACTION_ALGORITHM_VERSION = "warehouse-structure-v1"

_HASH_CHUNK_SIZE_BYTES = 1024 * 1024

STRUCTURE_ASSET_TYPE = "STRUCTURE_MAP"

STRUCTURE_DEBUG_ASSET_TYPE = "STRUCTURE_DEBUG"

EXTRACTION_TASK_NAME = "warehouse_mapping.extract_structure"

_PLACEHOLDER_FRAME_CHECKSUMS = {"", "0" * 64}

_EXTRACTION_STATE_TTL_S = 24 * 60 * 60

_EXTRACTION_STATE = BoundedTTLCache[dict[str, Any]](
    max_entries=256,
    ttl_seconds=_EXTRACTION_STATE_TTL_S,
)

_EXTRACTION_CELERY_PROBE_AT = BoundedTTLCache[float](max_entries=256, ttl_seconds=300.0)

_WORKER_READY_CACHE: tuple[float, bool, str | None] | None = None

_EXTRACTION_STATE_KEY_PREFIX = "warehouse:structure-extraction:v2"

_WORKER_READY_KEY = "warehouse:readiness:warehouse-mapping-worker:v1"

_WORKER_HEARTBEAT_PREFIX = "warehouse:readiness:warehouse-mapping-worker:heartbeat"

logger = logging.getLogger(__name__)
