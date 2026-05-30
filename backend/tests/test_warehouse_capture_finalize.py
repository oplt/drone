from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.modules.warehouse.service import capture_finalize as finalize_module
from backend.modules.warehouse.service.capture_finalize import (
    build_capture_result,
    persist_warehouse_ros_capture,
    resolve_capture_session_dir,
)
from backend.modules.warehouse.service.mapping import WarehouseScanMappingError


class _FakePerceptionPort:
    def __init__(self, artifact: Path) -> None:
        self.artifact = artifact
        self.downloaded_to: Path | None = None

    async def download_artifacts(self, *, flight_id: str, destination_dir: Path) -> list[str]:
        del flight_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        self.downloaded_to = destination_dir
        dst = destination_dir / self.artifact.name
        dst.write_text(self.artifact.read_text(encoding="utf-8"), encoding="utf-8")
        return [str(dst)]


class _FakeMappingService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def persist_capture(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"job_id": 99, "warehouse_map_id": kwargs["warehouse_map_id"], "status": "processing"}


def test_resolve_capture_session_dir_prefers_existing_directory(tmp_path: Path) -> None:
    session_dir = tmp_path / "flight_demo"
    session_dir.mkdir()
    resolved = resolve_capture_session_dir("demo", capture_root=tmp_path)
    assert resolved == session_dir.resolve()


def test_build_capture_result_reads_session_metadata(tmp_path: Path) -> None:
    session_dir = tmp_path / "flight_demo"
    session_dir.mkdir()
    (session_dir / "capture_metadata.json").write_text(
        (
            '{"warehouse_map_id": 7, "metadata": '
            '{"warehouse_name": "Aisle A", "polygon_local_m": [[0, 0], [1, 0], [1, 1]]}}'
        ),
        encoding="utf-8",
    )
    (session_dir / "mesh.ply").write_text("ply", encoding="utf-8")

    capture_result = build_capture_result(
        session_dir,
        mission_kind="warehouse_manual_mapping",
    )

    assert capture_result["file_count"] == 2
    assert capture_result["meta"]["warehouse_name"] == "Aisle A"
    assert capture_result["meta"]["warehouse_map_id"] == 7


def test_persist_warehouse_ros_capture_enqueues_mapping_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "mesh.ply"
    artifact.write_text("ply", encoding="utf-8")
    session_dir = tmp_path / "flight_demo"
    session_dir.mkdir()
    (session_dir / "capture_metadata.json").write_text(
        '{"warehouse_map_id": 7, "metadata": {"warehouse_name": "Aisle A"}}',
        encoding="utf-8",
    )
    port = _FakePerceptionPort(artifact)
    mapping = _FakeMappingService()
    monkeypatch.setattr(finalize_module, "WarehouseScanMappingService", lambda: mapping)

    result = asyncio.run(
        persist_warehouse_ros_capture(
            flight_id="demo",
            owner_id=3,
            org_id=1,
            source="warehouse_manual_mapping",
            stop_data={"session_dir": str(session_dir)},
            perception=port,
        )
    )

    assert result["job_id"] == 99
    assert port.downloaded_to == session_dir.resolve()
    assert mapping.calls
    assert mapping.calls[0]["warehouse_map_id"] == 7
    assert mapping.calls[0]["source"] == "warehouse_manual_mapping"


def test_persist_warehouse_ros_capture_requires_warehouse_map_id(tmp_path: Path) -> None:
    session_dir = tmp_path / "flight_demo"
    session_dir.mkdir()
    (session_dir / "mesh.ply").write_text("ply", encoding="utf-8")

    with pytest.raises(WarehouseScanMappingError):
        asyncio.run(
            persist_warehouse_ros_capture(
                flight_id="demo",
                owner_id=3,
                org_id=1,
                source="warehouse_manual_mapping",
                stop_data={"session_dir": str(session_dir)},
                perception=SimpleNamespace(download_artifacts=lambda **kwargs: []),
            )
        )


def test_session_has_mapping_artifacts_detects_mesh_and_ignores_metadata(tmp_path: Path) -> None:
    from backend.modules.warehouse.service.capture_finalize import session_has_mapping_artifacts

    session_dir = tmp_path / "flight_demo"
    session_dir.mkdir()
    (session_dir / "capture_metadata.json").write_text("{}", encoding="utf-8")
    assert session_has_mapping_artifacts(session_dir) is False
    (session_dir / "mesh.ply").write_text("ply", encoding="utf-8")
    assert session_has_mapping_artifacts(session_dir) is True


def test_persist_warehouse_ros_capture_rejects_metadata_only_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = tmp_path / "flight_demo"
    session_dir.mkdir()
    (session_dir / "capture_metadata.json").write_text(
        '{"warehouse_map_id": 7, "metadata": {"warehouse_name": "Aisle A"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("WAREHOUSE_CAPTURE_ARTIFACT_WAIT_S", "0")
    mapping = _FakeMappingService()
    monkeypatch.setattr(finalize_module, "WarehouseScanMappingService", lambda: mapping)

    with pytest.raises(WarehouseScanMappingError, match="did not produce a tileset"):
        asyncio.run(
            persist_warehouse_ros_capture(
                flight_id="demo",
                owner_id=3,
                org_id=1,
                source="warehouse_manual_mapping",
                stop_data={"session_dir": str(session_dir)},
                warehouse_map_id=7,
                perception=SimpleNamespace(download_artifacts=lambda **kwargs: []),
            )
        )
    assert not mapping.calls
