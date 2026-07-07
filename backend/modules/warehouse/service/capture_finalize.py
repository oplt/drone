from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Iterable

from backend.core.tokens import safe_token
from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
)

logger = logging.getLogger(__name__)

_ARTIFACT_SUFFIXES: frozenset[str] = frozenset(
    {".db3", ".mcap", ".bag", ".ply", ".pcd", ".glb", ".json", ".bt"}
)
_DEFAULT_CAPTURE_ROOT = Path("backend/storage/warehouse_ros/captures")


def safe_flight_token(raw: object) -> str:
    return safe_token(raw)


def resolve_capture_session_dir(
    flight_id: object,
    *,
    stop_data: dict[str, Any] | None = None,
) -> Path:
    if stop_data:
        for key in ("session_dir", "capture_dir", "output_dir"):
            value = stop_data.get(key)
            if value:
                return Path(str(value)).expanduser().resolve()
    return (_DEFAULT_CAPTURE_ROOT / f"flight_{safe_flight_token(flight_id)}").resolve()


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    return (p for p in root.rglob("*") if p.is_file())


def _count_files(root: Path) -> int:
    try:
        return sum(1 for _ in _iter_files(root))
    except OSError:
        logger.exception("Failed to count capture files under %s", root)
        return 0


def _contains_mapping_artifact(root: Path, suffixes: frozenset[str] = _ARTIFACT_SUFFIXES) -> bool:
    try:
        return any(p.suffix.lower() in suffixes for p in _iter_files(root))
    except OSError:
        logger.exception("Failed to scan mapping artifacts under %s", root)
        return False


async def wait_for_mapping_artifacts(
    session_dir: Path,
    *,
    timeout_s: float = 15.0,
    poll_interval_s: float = 1.0,
) -> bool:
    deadline = asyncio.get_running_loop().time() + max(0.0, float(timeout_s))
    poll = max(0.2, float(poll_interval_s))
    while True:
        if await asyncio.to_thread(_contains_mapping_artifact, session_dir):
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(poll)


async def start_warehouse_ros_mapping(
    *,
    flight_id: str,
    warehouse_map_id: int | None = None,
    metadata: dict[str, object] | None = None,
) -> WarehousePerceptionCommandResult:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    return await build_warehouse_perception_port().start_mapping(
        WarehouseMappingStartRequest(
            flight_id=safe_flight_token(flight_id),
            warehouse_map_id=warehouse_map_id,
            metadata=dict(metadata or {}),
        )
    )


async def stop_warehouse_ros_mapping(*, flight_id: str) -> WarehousePerceptionCommandResult:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    return await build_warehouse_perception_port().stop_mapping(
        flight_id=safe_flight_token(flight_id)
    )


async def persist_warehouse_ros_capture(
    *,
    flight_id: str,
    owner_id: int,
    org_id: int | None,
    source: str,
    stop_data: dict[str, Any] | None,
    warehouse_map_id: int,
    warehouse_name: str | None,
    db_flight_id: int | None,
    mission_kind: str,
) -> dict[str, Any]:
    from backend.modules.warehouse.service.mapping import WarehouseScanMappingService

    session_dir = resolve_capture_session_dir(flight_id, stop_data=stop_data)
    file_count = await asyncio.to_thread(_count_files, session_dir)
    status = "ready" if file_count > 0 else ("empty" if session_dir.exists() else "missing")

    capture_result = {
        "flight_id": safe_flight_token(flight_id),
        "source": source,
        "source_dir": session_dir.name,
        "absolute_dir": str(session_dir),
        "file_count": file_count,
        "status": status,
        "mission_kind": mission_kind,
    }
    return await WarehouseScanMappingService().persist_capture(
        owner_id=owner_id,
        org_id=org_id,
        warehouse_map_id=warehouse_map_id,
        warehouse_name=warehouse_name,
        polygon_local_m=[],
        session_dir=session_dir,
        capture_result=capture_result,
        reference_mapping_job_id=None,
        flight_id=db_flight_id,
        input_source=source,
    )
