from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import load_config
from .session import BridgeState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class MappingStartIn(BaseModel):
    flight_id: str
    warehouse_map_id: int | None = None
    profile: str | None = None
    sensor_rig_id: int | None = None
    capture_root: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)


class MappingStopIn(BaseModel):
    flight_id: str


class ArtifactDownloadIn(BaseModel):
    flight_id: str
    destination_dir: str


class ReplayStartIn(BaseModel):
    replay_id: str
    rosbag_path: str
    profile: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayStopIn(BaseModel):
    replay_id: str


config = load_config()
state = BridgeState(config)
app = FastAPI(title="Warehouse ROS 2 Mapping Bridge")
logger.info(
    (
        "Warehouse ROS bridge service configured "
        "host=%s port=%s profile=%s capture_root=%s ws=%s autolaunch=%s"
    ),
    config.host,
    config.port,
    config.profile,
    config.capture_root,
    config.ros_ws_url,
    config.autolaunch,
    extra={
        "host": config.host,
        "port": config.port,
        "profile": config.profile,
        "capture_root": str(config.capture_root),
        "ros_ws_url": config.ros_ws_url,
        "autolaunch": config.autolaunch,
    },
)


@app.get("/health")
async def health(deep: bool = False, force: bool = False) -> dict[str, Any]:
    path = "/health?deep=1" if deep else "/health"
    if force:
        path = f"{path}&force=1" if "?" in path else f"{path}?force=1"
    started = time.perf_counter()

    if deep:
        payload = await asyncio.to_thread(state.health, deep=True, force=force)
    else:
        payload = state.health(deep=False, force=force)

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    payload["duration_ms"] = duration_ms

    logger.info(
        "Warehouse bridge health path=%s deep=%s from_cache=%s duration_ms=%s probe_in_progress=%s",
        path,
        deep,
        bool(payload.get("from_cache", False)),
        duration_ms,
        bool(payload.get("probe_in_progress", False)),
    )

    return payload


@app.get("/ready")
async def ready(force: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    payload = await asyncio.to_thread(state.health, deep=True, force=force)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    blockers = list(components.get("missing_required_topics") or [])
    if components.get("diagnostics_pending"):
        blockers.append("diagnostics_pending")
    if components.get("ros_topic_probe_error"):
        blockers.append("ros_topic_probe_error")
    ready_payload = {
        **payload,
        "ready": bool(payload.get("ready")),
        "state": "ready" if payload.get("ready") else "blocked",
        "blockers": list(dict.fromkeys(str(item) for item in blockers if item)),
        "retry_after_ms": 1000 if not payload.get("ready") else 0,
        "duration_ms": duration_ms,
    }
    logger.info(
        "Warehouse bridge ready path=/ready ready=%s state=%s duration_ms=%s blockers=%s",
        ready_payload["ready"],
        ready_payload["state"],
        duration_ms,
        ready_payload["blockers"],
    )
    return ready_payload


@app.get("/exploration/snapshot")
async def exploration_snapshot() -> dict[str, Any]:
    return await asyncio.to_thread(state.exploration_snapshot)


@app.post("/mapping/start")
async def start_mapping(payload: MappingStartIn) -> dict[str, Any]:
    logger.info(
        "Warehouse bridge API mapping start flight_id=%s map_id=%s sensor_rig_id=%s",
        payload.flight_id,
        payload.warehouse_map_id,
        payload.sensor_rig_id,
        extra={
            "flight_id": payload.flight_id,
            "warehouse_map_id": payload.warehouse_map_id,
            "sensor_rig_id": payload.sensor_rig_id,
        },
    )
    return await asyncio.to_thread(state.start_mapping, payload.model_dump(mode="python"))


@app.post("/mapping/stop")
async def stop_mapping(payload: MappingStopIn) -> dict[str, Any]:
    logger.info(
        "Warehouse bridge API mapping stop flight_id=%s",
        payload.flight_id,
        extra={"flight_id": payload.flight_id},
    )
    return await asyncio.to_thread(state.stop_mapping, payload.flight_id)


@app.post("/mapping/artifacts/download")
async def download_artifacts(payload: ArtifactDownloadIn) -> dict[str, Any]:
    logger.info(
        "Warehouse bridge API artifact download",
        extra={"flight_id": payload.flight_id, "destination_dir": payload.destination_dir},
    )
    return await asyncio.to_thread(
        state.download_artifacts, payload.flight_id, Path(payload.destination_dir)
    )


@app.post("/replay/start")
async def start_replay(payload: ReplayStartIn) -> dict[str, Any]:
    logger.info(
        "Warehouse bridge API replay start",
        extra={"replay_id": payload.replay_id, "rosbag_path": payload.rosbag_path},
    )
    return await asyncio.to_thread(state.start_replay, payload.model_dump(mode="python"))


@app.post("/replay/stop")
async def stop_replay(payload: ReplayStopIn) -> dict[str, Any]:
    logger.info("Warehouse bridge API replay stop", extra={"replay_id": payload.replay_id})
    return await asyncio.to_thread(state.stop_replay, payload.replay_id)


def main() -> None:
    logger.info("Starting Warehouse ROS bridge service")
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()
