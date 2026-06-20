from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.modules.warehouse.service import live_map_diagnostics


@pytest.mark.asyncio
async def test_live_map_diagnostics_reuses_cached_report() -> None:
    live_map_diagnostics.clear_live_map_diagnostics_cache()
    report = live_map_diagnostics.WarehouseLiveMapDiagnostics(tf_ok=True)

    with patch.object(
        live_map_diagnostics,
        "_collect_live_map_diagnostics",
        AsyncMock(return_value=report),
    ) as collect:
        first = await live_map_diagnostics.run_live_map_diagnostics(cache_ttl_s=45)
        first.warnings.append("caller mutation")
        second = await live_map_diagnostics.run_live_map_diagnostics(cache_ttl_s=45)

    assert collect.await_count == 1
    assert second.tf_ok is True
    assert second.warnings == []


@pytest.mark.asyncio
async def test_live_map_diagnostics_force_refresh_bypasses_cache() -> None:
    live_map_diagnostics.clear_live_map_diagnostics_cache()
    collect = AsyncMock(
        side_effect=[
            live_map_diagnostics.WarehouseLiveMapDiagnostics(tf_message="first"),
            live_map_diagnostics.WarehouseLiveMapDiagnostics(tf_message="second"),
        ]
    )

    with patch.object(live_map_diagnostics, "_collect_live_map_diagnostics", collect):
        await live_map_diagnostics.run_live_map_diagnostics(cache_ttl_s=45)
        refreshed = await live_map_diagnostics.run_live_map_diagnostics(
            force=True,
            cache_ttl_s=45,
        )

    assert collect.await_count == 2
    assert refreshed.tf_message == "second"
