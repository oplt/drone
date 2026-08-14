"""Colored point-cloud live-map bridge — source resolution."""

from __future__ import annotations

from backend.modules.warehouse.service.map_source_config import (
    WAREHOUSE_LIVE_MAP_SOURCES,
    LiveMapSourceConfig,
)

from .state import _ColoredBridgeRuntime


def _runtime_busy(runtime: _ColoredBridgeRuntime) -> bool:
    for source in runtime.sources.values():
        with source.lock:
            if source.processing or source.queued_msg is not None:
                return True
    return False


def _sources_with_late_publisher_fallbacks(
    resolved_sources: dict[str, LiveMapSourceConfig],
    source_ids: tuple[str, ...],
) -> tuple[dict[str, LiveMapSourceConfig], set[str]]:
    requested_sources = set(source_ids)
    sources = {
        source_id: config
        for source_id, config in resolved_sources.items()
        if source_id in requested_sources
    }
    missing_sources = requested_sources.difference(resolved_sources)
    for source_id in missing_sources:
        configured = WAREHOUSE_LIVE_MAP_SOURCES.get(source_id)
        if configured is not None and configured.kind in {"point_cloud", "esdf"}:
            sources[source_id] = configured
    return sources, missing_sources


__all__ = ["_runtime_busy", "_sources_with_late_publisher_fallbacks"]
