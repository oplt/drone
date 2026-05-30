from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from time import monotonic
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.warehouse.perception import build_warehouse_perception_port
from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
    WarehousePerceptionPort,
)
from backend.modules.warehouse.service.mapping import (
    WarehouseScanMappingError,
    WarehouseScanMappingService,
)

logger = logging.getLogger(__name__)

_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")

_METADATA_ONLY_FILES = {
    "capture_metadata.json",
    "warehouse_mapping_manifest.json",
    "mapping_health_summary.json",
    "artifact_index.json",
    "capture_session.json",
    "mapping_stop.json",
    "mapping_quality_report.json",
    "quality_report.json",
    "replay_manifest.json",
    "replay_stop.json",
}

_MAPPING_ARTIFACT_EXTENSIONS = {
    ".glb",
    ".gltf",
    ".obj",
    ".ply",
    ".pcd",
    ".las",
    ".laz",
    ".e57",
    ".db3",
    ".mcap",
    ".bag",
    ".tsdf",
    ".esdf",
}


def safe_flight_token(raw: Any) -> str:
    token = _UNSAFE_TOKEN_CHARS.sub("_", str(raw or "")).strip("._-")
    return token or "unknown"


def session_has_mapping_artifacts(session_dir: Path) -> bool:
    if not session_dir.exists():
        return False
    if any(session_dir.rglob("tileset.json")):
        return True
    for path in session_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in _METADATA_ONLY_FILES:
            continue
        suffix = path.suffix.lower()
        if suffix in _MAPPING_ARTIFACT_EXTENSIONS:
            return True
    return False


def describe_session_capture(session_dir: Path) -> dict[str, Any]:
    files = sorted(
        path.name
        for path in session_dir.rglob("*")
        if path.is_file()
    ) if session_dir.exists() else []
    metadata_only = [name for name in files if name in _METADATA_ONLY_FILES]
    return {
        "session_dir": str(session_dir),
        "file_count": len(files),
        "metadata_files": metadata_only,
        "has_mapping_artifacts": session_has_mapping_artifacts(session_dir),
    }


def missing_artifacts_message(session_dir: Path) -> str:
    summary = describe_session_capture(session_dir)
    metadata = ", ".join(summary["metadata_files"]) or "none"
    return (
        "Warehouse capture did not produce a tileset, point cloud, or ROS artifact. "
        f"Session {summary['session_dir']} contains {summary['file_count']} file(s) "
        f"({metadata}). "
        "Start the ROS nvblox mapping stack before mapping (set WAREHOUSE_ROS_AUTOLAUNCH=1 "
        "on the bridge or launch isaac_warehouse_mapping manually), verify camera/lidar topics "
        "in ROS Mapping Health, fly while mapping is active, then stop mapping and wait a few "
        "seconds for export."
    )


async def wait_for_mapping_artifacts(
    session_dir: Path,
    *,
    timeout_s: float | None = None,
    poll_interval_s: float = 2.0,
) -> bool:
    if timeout_s is None:
        timeout_s = float(os.getenv("WAREHOUSE_CAPTURE_ARTIFACT_WAIT_S", "45"))
    deadline = monotonic() + max(0.0, timeout_s)
    while monotonic() < deadline:
        if session_has_mapping_artifacts(session_dir):
            return True
        await asyncio.sleep(max(0.2, poll_interval_s))
    return session_has_mapping_artifacts(session_dir)


def resolve_capture_session_dir(
    flight_id: str,
    *,
    capture_root: str | Path | None = None,
    stop_data: dict[str, Any] | None = None,
) -> Path:
    root = Path(capture_root or settings.WAREHOUSE_ROS_CAPTURE_ROOT).resolve()
    token = safe_flight_token(flight_id)
    candidates: list[Path] = []
    if isinstance(stop_data, dict):
        for key in ("session_dir", "absolute_dir", "capture_dir"):
            raw = stop_data.get(key)
            if isinstance(raw, str) and raw.strip():
                candidates.append(Path(raw))
    candidates.extend(
        [
            root / f"flight_{token}",
            root / token,
            root / f"flight_{flight_id}",
            root / str(flight_id),
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    return (root / f"flight_{token}").resolve()


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _polygon_from_raw(raw: Any) -> list[tuple[float, float]]:
    if not isinstance(raw, list):
        return []
    polygon: list[tuple[float, float]] = []
    for point in raw:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            polygon.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            continue
    return polygon


def build_capture_result(
    session_dir: Path,
    *,
    mission_kind: str,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = [path for path in session_dir.rglob("*") if path.is_file()]
    merged_meta: dict[str, Any] = {"mission_kind": mission_kind}
    for name in (
        "capture_metadata.json",
        "warehouse_mapping_manifest.json",
        "capture_session.json",
    ):
        payload = _read_json_dict(session_dir / name)
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            merged_meta.update(metadata)
        for key in ("warehouse_map_id", "warehouse_name", "source", "scenario_name"):
            if key in payload and payload[key] not in (None, ""):
                merged_meta.setdefault(key, payload[key])
    if extra_meta:
        merged_meta.update(extra_meta)
    return {
        "absolute_dir": str(session_dir),
        "source_dir": str(session_dir),
        "file_count": len(files),
        "status": "staged" if files else "empty",
        "meta": merged_meta,
    }


def _resolve_capture_context(
    session_dir: Path,
    capture_result: dict[str, Any],
    *,
    warehouse_map_id: int | None,
    warehouse_name: str | None,
    polygon_local_m: list[tuple[float, float]] | None,
) -> tuple[int | None, str | None, list[tuple[float, float]]]:
    meta = capture_result.get("meta")
    meta_dict = meta if isinstance(meta, dict) else {}
    resolved_map_id = warehouse_map_id
    if resolved_map_id is None:
        raw_map_id = meta_dict.get("warehouse_map_id")
        try:
            resolved_map_id = int(raw_map_id) if raw_map_id is not None else None
        except (TypeError, ValueError):
            resolved_map_id = None
    resolved_name = (warehouse_name or "").strip() or None
    if resolved_name is None:
        raw_name = meta_dict.get("warehouse_name")
        resolved_name = str(raw_name).strip() if isinstance(raw_name, str) and raw_name.strip() else None
    resolved_polygon = list(polygon_local_m or [])
    if not resolved_polygon:
        resolved_polygon = _polygon_from_raw(meta_dict.get("polygon_local_m"))
    return resolved_map_id, resolved_name, resolved_polygon


async def start_warehouse_ros_mapping(
    *,
    flight_id: str,
    warehouse_map_id: int | None,
    sensor_rig_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    perception: WarehousePerceptionPort | None = None,
) -> WarehousePerceptionCommandResult:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        ensure_warehouse_mapping_stack_running,
        mapping_stack_not_running_result,
    )

    stack_status = await ensure_warehouse_mapping_stack_running()
    if not stack_status.running:
        return mapping_stack_not_running_result()
    port = perception or build_warehouse_perception_port()
    return await port.start_mapping(
        WarehouseMappingStartRequest(
            flight_id=flight_id,
            warehouse_map_id=warehouse_map_id,
            sensor_rig_id=sensor_rig_id,
            metadata=metadata or {},
        )
    )


async def stop_warehouse_ros_mapping(
    *,
    flight_id: str,
    perception: WarehousePerceptionPort | None = None,
) -> WarehousePerceptionCommandResult:
    port = perception or build_warehouse_perception_port()
    return await port.stop_mapping(flight_id=flight_id)


async def persist_warehouse_ros_capture(
    *,
    flight_id: str,
    owner_id: int,
    org_id: int | None,
    source: str,
    stop_data: dict[str, Any] | None = None,
    warehouse_map_id: int | None = None,
    warehouse_name: str | None = None,
    polygon_local_m: list[tuple[float, float]] | None = None,
    reference_mapping_job_id: int | None = None,
    db_flight_id: int | None = None,
    mission_kind: str | None = None,
    perception: WarehousePerceptionPort | None = None,
) -> dict[str, Any]:
    port = perception or build_warehouse_perception_port()
    session_dir = resolve_capture_session_dir(
        flight_id,
        stop_data=stop_data,
    )
    session_dir.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = await port.download_artifacts(
            flight_id=flight_id,
            destination_dir=session_dir,
        )
    except Exception:
        logger.exception(
            "Warehouse capture artifact download failed flight_id=%s session_dir=%s",
            flight_id,
            session_dir,
        )
        downloaded = []

    capture_result = build_capture_result(
        session_dir,
        mission_kind=mission_kind or source,
        extra_meta={
            "flight_id": flight_id,
            "perception_artifacts_count": len(downloaded),
        },
    )

    await wait_for_mapping_artifacts(session_dir)
    if not session_has_mapping_artifacts(session_dir):
        raise WarehouseScanMappingError(missing_artifacts_message(session_dir))

    resolved_map_id, resolved_name, resolved_polygon = _resolve_capture_context(
        session_dir,
        capture_result,
        warehouse_map_id=warehouse_map_id,
        warehouse_name=warehouse_name,
        polygon_local_m=polygon_local_m,
    )
    if resolved_map_id is None:
        raise WarehouseScanMappingError(
            "Warehouse capture persistence requires warehouse_map_id in session metadata."
        )

    return await WarehouseScanMappingService().persist_capture(
        owner_id=owner_id,
        org_id=org_id,
        warehouse_map_id=resolved_map_id,
        warehouse_name=resolved_name,
        polygon_local_m=resolved_polygon,
        session_dir=session_dir,
        capture_result=capture_result,
        reference_mapping_job_id=reference_mapping_job_id,
        flight_id=db_flight_id,
        source=source,
    )
