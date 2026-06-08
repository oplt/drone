from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
)

_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_flight_token(raw: object) -> str:
    token = _UNSAFE_TOKEN_CHARS.sub("_", str(raw or "")).strip("._-")
    return token or "unknown"


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
    return Path("backend/storage/warehouse_ros/captures") / f"flight_{safe_flight_token(flight_id)}"


async def wait_for_mapping_artifacts(
    session_dir: Path,
    *,
    timeout_s: float = 15.0,
    poll_interval_s: float = 1.0,
) -> bool:
    suffixes = {".db3", ".mcap", ".bag", ".ply", ".pcd", ".glb", ".json", ".bt"}
    deadline = asyncio.get_running_loop().time() + max(0.0, timeout_s)
    while True:
        if session_dir.exists() and any(
            p.is_file() and p.suffix.lower() in suffixes for p in session_dir.rglob("*")
        ):
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(max(0.2, poll_interval_s))


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
            metadata=metadata or {},
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
    capture_result = {
        "flight_id": safe_flight_token(flight_id),
        "source": source,
        "source_dir": session_dir.name,
        "absolute_dir": str(session_dir),
        "file_count": (
            len([p for p in session_dir.rglob("*") if p.is_file()])
            if session_dir.exists()
            else 0
        ),
        "status": "ready" if session_dir.exists() else "missing",
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
