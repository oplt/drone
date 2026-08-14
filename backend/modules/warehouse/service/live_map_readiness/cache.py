"""Warehouse live-map readiness — readiness caches and warm-up."""

from __future__ import annotations


import asyncio
import json
import logging
import time
from dataclasses import asdict

from backend.infrastructure.cache.redis import get_sync_redis_client

logger = logging.getLogger(__name__)
from .constants import _RGBD_READINESS_KEY, _TOPIC_PROBE_KEY
from .models import MappingReadinessResult, TopicTypeProbe

_rgbd_readiness_cache: MappingReadinessResult | None = None
_rgbd_readiness_cache_at: float = 0.0
_rgbd_warmup_lock = asyncio.Lock()
_rgbd_warmup_running = False

_topic_probe_cache: tuple[list[TopicTypeProbe], dict[str, str | None]] | None = None
_topic_probe_cache_at: float = 0.0

def invalidate_readiness_caches() -> None:
    """Drop diagnostics after bridge/config changes; safety checks still probe fresh."""
    global _rgbd_readiness_cache, _rgbd_readiness_cache_at
    global _topic_probe_cache, _topic_probe_cache_at
    _rgbd_readiness_cache = None
    _rgbd_readiness_cache_at = 0.0
    _topic_probe_cache = None
    _topic_probe_cache_at = 0.0
    try:
        client = get_sync_redis_client()
        client.delete(_RGBD_READINESS_KEY, _TOPIC_PROBE_KEY)
    except Exception:
        logger.debug("warehouse_readiness_cache_invalidation_failed", exc_info=True)

def _rgbd_readiness_cache_ttl_s() -> float:
    from backend.core.config.runtime import settings

    return max(0.0, float(getattr(settings, "warehouse_rgbd_readiness_cache_ttl_s", 30.0)))

def _topic_probe_cache_ttl_s() -> float:
    from backend.core.config.runtime import settings

    return max(0.0, float(getattr(settings, "warehouse_live_map_topic_probe_cache_ttl_s", 15.0)))

def _store_rgbd_readiness_cache(result: MappingReadinessResult) -> None:
    global _rgbd_readiness_cache, _rgbd_readiness_cache_at
    if result.ready:
        _rgbd_readiness_cache = result
        _rgbd_readiness_cache_at = time.monotonic()
        try:
            get_sync_redis_client().setex(
                _RGBD_READINESS_KEY,
                max(1, int(_rgbd_readiness_cache_ttl_s())),
                json.dumps(
                    {
                        "ready": result.ready,
                        "missing_topics": result.missing_topics,
                        "topic_probes": [asdict(probe) for probe in result.topic_probes],
                        "warnings": result.warnings,
                        "rgbd_pointcloud_topic": result.rgbd_pointcloud_topic,
                        "rgbd_input_topics_ready": result.rgbd_input_topics_ready,
                        "nvblox_pointcloud_topics": result.nvblox_pointcloud_topics,
                        "timing_ms": result.timing_ms,
                    },
                    separators=(",", ":"),
                ),
            )
        except Exception:
            logger.debug("rgbd_readiness_shared_state_unavailable", exc_info=True)

def peek_cached_rgbd_readiness(*, max_age_s: float | None = None) -> MappingReadinessResult | None:
    """Return a recent successful RGB-D readiness result, if any."""
    try:
        payload = get_sync_redis_client().get(_RGBD_READINESS_KEY)
        if payload:
            raw = json.loads(payload)
            return MappingReadinessResult(
                ready=bool(raw.get("ready")),
                missing_topics=list(raw.get("missing_topics") or []),
                topic_probes=[TopicTypeProbe(**item) for item in raw.get("topic_probes") or []],
                warnings=list(raw.get("warnings") or []),
                rgbd_pointcloud_topic=raw.get("rgbd_pointcloud_topic"),
                rgbd_input_topics_ready=bool(raw.get("rgbd_input_topics_ready")),
                nvblox_pointcloud_topics=list(raw.get("nvblox_pointcloud_topics") or []),
                timing_ms=dict(raw.get("timing_ms") or {}),
            )
    except Exception:
        logger.debug("rgbd_readiness_shared_state_read_failed", exc_info=True)
    if _rgbd_readiness_cache is None:
        return None
    ttl = _rgbd_readiness_cache_ttl_s() if max_age_s is None else max(0.0, max_age_s)
    if ttl <= 0.0:
        return None
    if (time.monotonic() - _rgbd_readiness_cache_at) >= ttl:
        return None
    return _rgbd_readiness_cache

async def warm_rgbd_readiness_background(*, timeout_s: float = 90.0) -> None:
    """Poll RGB-D topics in the background during preflight warm-up."""
    global _rgbd_warmup_running

    cached = peek_cached_rgbd_readiness()
    if cached is not None and cached.ready:
        return

    async with _rgbd_warmup_lock:
        cached = peek_cached_rgbd_readiness()
        if cached is not None and cached.ready:
            return
        if _rgbd_warmup_running:
            return
        _rgbd_warmup_running = True

    try:
        from .rgbd_wait import wait_for_rgbd_mapping_topics

        result = await wait_for_rgbd_mapping_topics(timeout_s=max(5.0, timeout_s))
        if result.ready:
            logger.info(
                "Background RGB-D readiness warm-up complete (topic=%r)",
                result.rgbd_pointcloud_topic,
            )
    except Exception:
        logger.debug("Background RGB-D readiness warm-up failed", exc_info=True)
    finally:
        async with _rgbd_warmup_lock:
            _rgbd_warmup_running = False

async def warm_live_map_ros_graph() -> None:
    """Pre-run topic probes and rclpy init so bridge start is faster at takeoff."""

    def _warm_sync() -> None:
        from .topic_probes import probe_live_map_topic_types

        probe_live_map_topic_types(quiet=True, use_cache=True)
        try:
            import rclpy

            if not rclpy.ok():
                rclpy.init(args=None)
        except Exception:
            logger.debug("rclpy pre-init during live-map warm-up skipped", exc_info=True)

    await asyncio.to_thread(_warm_sync)
