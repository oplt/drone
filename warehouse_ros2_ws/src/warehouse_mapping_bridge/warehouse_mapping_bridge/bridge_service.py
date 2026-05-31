from __future__ import annotations

import asyncio
import logging
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
async def health(deep: bool = False) -> dict[str, Any]:
    return await asyncio.to_thread(state.health, deep=deep)


@app.get("/exploration/snapshot")
async def exploration_snapshot() -> dict[str, Any]:
    return state.exploration_snapshot()


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
    return state.start_mapping(payload.model_dump(mode="python"))


@app.post("/mapping/stop")
async def stop_mapping(payload: MappingStopIn) -> dict[str, Any]:
    logger.info(
        "Warehouse bridge API mapping stop flight_id=%s",
        payload.flight_id,
        extra={"flight_id": payload.flight_id},
    )
    return state.stop_mapping(payload.flight_id)


@app.post("/mapping/artifacts/download")
async def download_artifacts(payload: ArtifactDownloadIn) -> dict[str, Any]:
    logger.info(
        "Warehouse bridge API artifact download",
        extra={"flight_id": payload.flight_id, "destination_dir": payload.destination_dir},
    )
    return state.download_artifacts(payload.flight_id, Path(payload.destination_dir))


@app.post("/replay/start")
async def start_replay(payload: ReplayStartIn) -> dict[str, Any]:
    logger.info(
        "Warehouse bridge API replay start",
        extra={"replay_id": payload.replay_id, "rosbag_path": payload.rosbag_path},
    )
    return state.start_replay(payload.model_dump(mode="python"))


@app.post("/replay/stop")
async def stop_replay(payload: ReplayStopIn) -> dict[str, Any]:
    logger.info("Warehouse bridge API replay stop", extra={"replay_id": payload.replay_id})
    return state.stop_replay(payload.replay_id)


def main() -> None:
    logger.info("Starting Warehouse ROS bridge service")
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
