from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from types import SimpleNamespace

from backend.services.patrol.patrol_persistence import PatrolPersistenceService


@dataclass
class _GeoPoint:
    lat: float
    lon: float


@dataclass
class _Anomaly:
    event_type: str
    confidence: float
    location: _GeoPoint
    payload: dict


@dataclass
class _Packet:
    frame_id: int


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persist one simulated patrol anomaly through PatrolPersistenceService."
    )
    parser.add_argument("--flight-id", type=int, required=True, help="DB flight_id to attach the simulated anomaly to.")
    parser.add_argument("--client-flight-id", type=str, default="sim-flight-001")
    parser.add_argument(
        "--mission-task-type",
        type=str,
        default="event_triggered_patrol",
        choices=[
            "perimeter_patrol",
            "waypoint_patrol",
            "grid_surveillance",
            "event_triggered_patrol",
        ],
    )
    parser.add_argument(
        "--allowed-ai-task",
        action="append",
        default=[],
        help="Allowed patrol AI task. Repeatable. Defaults to all standard patrol AI tasks.",
    )
    parser.add_argument("--trigger-type", type=str, default="fence_alarm")
    parser.add_argument("--target-label", type=str, default="person")
    parser.add_argument("--event-type", type=str, default="restricted_zone_entry")
    parser.add_argument("--object-class", type=str, default="person")
    parser.add_argument("--track-id", type=str, default="trk-sim-1")
    parser.add_argument("--zone-name", type=str, default="gate_north")
    parser.add_argument("--checkpoint-index", type=int, default=None)
    parser.add_argument("--confidence", type=float, default=0.93)
    parser.add_argument("--frame-id", type=int, default=1)
    parser.add_argument("--lat", type=float, default=50.123456)
    parser.add_argument("--lon", type=float, default=4.123456)
    parser.add_argument("--alt", type=float, default=35.0)
    parser.add_argument("--heading", type=float, default=92.0)
    parser.add_argument("--groundspeed", type=float, default=5.4)
    parser.add_argument("--snapshot-path", type=str, default="/tmp/patrol_sim_snapshot.jpg")
    parser.add_argument("--clip-path", type=str, default="/tmp/patrol_sim_clip.mp4")
    parser.add_argument("--model-name", type=str, default="yolov8n")
    parser.add_argument("--model-version", type=str, default="8.2.0")
    args = parser.parse_args()

    allowed_ai_tasks = args.allowed_ai_task or [
        "intruder_detection",
        "vehicle_detection",
        "fence_breach_detection",
        "motion_detection",
    ]

    async def _fake_runtime_context():
        return {
            "client_flight_id": args.client_flight_id,
            "db_flight_id": args.flight_id,
            "mission_type": "private_patrol",
            "mission_task_type": args.mission_task_type,
            "private_patrol_ai_tasks": allowed_ai_tasks,
            "private_patrol_trigger_type": args.trigger_type,
            "private_patrol_target_label": args.target_label,
        }

    service = PatrolPersistenceService(runtime_context_provider=_fake_runtime_context)

    anomaly = _Anomaly(
        event_type=args.event_type,
        confidence=args.confidence,
        location=_GeoPoint(lat=args.lat, lon=args.lon),
        payload={
            "object_class": args.object_class,
            "track_id": args.track_id,
            "zone_name": args.zone_name,
            "checkpoint_index": args.checkpoint_index,
            "bbox": [241, 122, 377, 411],
            "centroid": [309, 266],
            "source": "rgb",
            "snapshot_path": args.snapshot_path,
            "clip_path": args.clip_path,
            "model_name": args.model_name,
            "model_version": args.model_version,
        },
    )
    packet = _Packet(frame_id=args.frame_id)
    telemetry = {
        "id": None,
        "lat": args.lat,
        "lon": args.lon,
        "alt": args.alt,
        "heading": args.heading,
        "groundspeed": args.groundspeed,
    }
    motion_meta = {"simulated": True, "max_motion_area": 4200, "num_regions": 1}

    result = await service.persist_anomaly(
        anomaly=anomaly,
        packet=packet,
        telemetry=telemetry,
        motion_meta=motion_meta,
    )

    print(json.dumps(asdict(result) if result else {"result": None}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
