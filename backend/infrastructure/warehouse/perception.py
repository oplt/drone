from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import httpx

from backend.core.config.runtime import settings
from backend.modules.warehouse.ports import (
    WarehouseExplorationSnapshot,
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
    WarehousePerceptionStatus,
    WarehouseReplayStartRequest,
)


def _odometry_overlay() -> dict[str, Any]:
    path_raw = str(getattr(settings, "WAREHOUSE_ODOMETRY_STATE_PATH", "") or "").strip()
    if not path_raw:
        return {}
    path = Path(path_raw)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _capture_disk_metrics(capture_root: Path) -> dict[str, Any]:
    """Local free space for the warehouse capture directory (no bridge HTTP required)."""
    try:
        usage = shutil.disk_usage(capture_root)
    except OSError:
        return {}
    free_gb = usage.free / 1_000_000_000.0
    return {
        "disk_free_gb": free_gb,
        "disk_free_bytes": float(usage.free),
        "disk": {
            "path": str(capture_root),
            "free_gb": free_gb,
            "total_gb": usage.total / 1_000_000_000.0,
        },
    }


def _merge_capture_disk(components: dict[str, Any], capture_root: Path) -> dict[str, Any]:
    merged = dict(components)
    if merged.get("disk_free_gb") is not None:
        return merged
    disk = merged.get("disk")
    if isinstance(disk, dict) and disk.get("free_gb") is not None:
        return merged
    merged.update(_capture_disk_metrics(capture_root))
    return merged


class WarehousePerceptionHttpPort:
    def __init__(self) -> None:
        self.bridge_url = str(getattr(settings, "WAREHOUSE_ROS_BRIDGE_URL", "") or "").strip()
        self.capture_root = Path(settings.WAREHOUSE_ROS_CAPTURE_ROOT).resolve()
        self.capture_root.mkdir(parents=True, exist_ok=True)

    async def status(self, *, deep: bool = False, force: bool = False) -> WarehousePerceptionStatus:
        del force
        components = _odometry_overlay()
        reachable = False
        detail = None
        if self.bridge_url and deep:
            url = self.bridge_url.rstrip("/") + "/health"
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(url)
                reachable = response.status_code < 400
                detail = f"Bridge health HTTP {response.status_code}"
                try:
                    body = response.json()
                except Exception:
                    body = {}
                if isinstance(body, dict):
                    body_components = body.get("components")
                    if isinstance(body_components, dict):
                        components.update(body_components)
            except Exception as exc:
                detail = f"Bridge health unreachable: {exc}"
        else:
            reachable = bool(self.bridge_url or components)
            detail = "Bridge URL configured; deep probe not requested." if self.bridge_url else None
        ready = bool(
            reachable
            and (
                components.get("local_position_ok")
                or components.get("slam_ready")
                or components.get("slam_tracking_ok")
            )
        )
        components = _merge_capture_disk(components, self.capture_root)
        return WarehousePerceptionStatus(
            configured=bool(self.bridge_url or components),
            reachable=reachable,
            ready=ready,
            status="ready" if ready else ("configured" if reachable else "unavailable"),
            profile=settings.warehouse_ros_profile or None,
            bridge_flow=settings.WAREHOUSE_BRIDGE_FLOW,
            bridge_url=self.bridge_url or None,
            capture_root=str(self.capture_root),
            detail=detail,
            components=components,
        )

    async def exploration_snapshot(self) -> WarehouseExplorationSnapshot:
        return WarehouseExplorationSnapshot(metadata={"source": "warehouse_perception_http"})

    async def start_mapping(
        self, request: WarehouseMappingStartRequest
    ) -> WarehousePerceptionCommandResult:
        session_dir = self.capture_root / f"flight_{request.flight_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        if self.bridge_url:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        self.bridge_url.rstrip("/") + "/mapping/start",
                        json=request.model_dump(mode="json"),
                    )
                if response.status_code < 400:
                    data = response.json() if response.content else {}
                    return WarehousePerceptionCommandResult(
                        accepted=True,
                        status=(
                            str(data.get("status") or "started")
                            if isinstance(data, dict)
                            else "started"
                        ),
                        detail=None,
                        data=data if isinstance(data, dict) else {},
                    )
            except Exception:
                pass
        return WarehousePerceptionCommandResult(
            accepted=True,
            status="local_session_started",
            detail=(
                "No warehouse ROS bridge start endpoint configured; "
                "using local capture directory."
            ),
            data={"session_dir": str(session_dir), "capture_root": str(self.capture_root)},
        )

    async def stop_mapping(self, *, flight_id: str) -> WarehousePerceptionCommandResult:
        session_dir = self.capture_root / f"flight_{flight_id}"
        if self.bridge_url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        self.bridge_url.rstrip("/") + "/mapping/stop",
                        json={"flight_id": flight_id},
                    )
                if response.status_code < 400:
                    data = response.json() if response.content else {}
                    return WarehousePerceptionCommandResult(
                        accepted=True,
                        status=(
                            str(data.get("status") or "stopped")
                            if isinstance(data, dict)
                            else "stopped"
                        ),
                        data=data if isinstance(data, dict) else {},
                    )
            except Exception:
                pass
        return WarehousePerceptionCommandResult(
            accepted=True,
            status="local_session_stopped",
            data={"session_dir": str(session_dir)},
        )

    async def download_artifacts(self, *, flight_id: str, destination_dir: Path) -> list[str]:
        src_dir = self.capture_root / f"flight_{flight_id}"
        destination_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        if not src_dir.exists():
            return copied
        for src in src_dir.rglob("*"):
            if not src.is_file():
                continue
            dst = destination_dir / src.name
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
            copied.append(str(dst))
        return copied

    async def start_replay(
        self, request: WarehouseReplayStartRequest
    ) -> WarehousePerceptionCommandResult:
        return WarehousePerceptionCommandResult(
            accepted=False,
            status="unsupported",
            detail=f"Replay is not configured for {request.replay_id}.",
        )

    async def stop_replay(self, *, replay_id: str) -> WarehousePerceptionCommandResult:
        return WarehousePerceptionCommandResult(
            accepted=True,
            status="stopped",
            detail=f"Replay {replay_id} stopped.",
        )


def build_warehouse_perception_port() -> WarehousePerceptionHttpPort:
    return WarehousePerceptionHttpPort()
