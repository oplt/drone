from __future__ import annotations

from typing import Any

from backend.modules.livestock.models import HerdTask


def build_mission(task: HerdTask, latest: list[dict[str, Any]]) -> dict[str, Any]:
    lat_c = sum(p["lat"] for p in latest) / len(latest)
    lon_c = sum(p["lon"] for p in latest) / len(latest)

    if task.type == "census":
        return {
            "type": "route",
            "waypoints": [
                {
                    "lat": lat_c,
                    "lon": lon_c,
                    "alt": task.params.get("altitude_msl", 30.0),
                }
            ],
            "speed": task.params.get("speed", 8.0),
            "altitude_agl": task.params.get("altitude_agl", 30.0),
        }

    if task.type == "herd_sweep":
        d = float(task.params.get("box_deg", 0.0008))
        alt = float(task.params.get("altitude_msl", 35.0))
        return {
            "type": "route",
            "waypoints": [
                {"lat": lat_c + d, "lon": lon_c - d, "alt": alt},
                {"lat": lat_c + d, "lon": lon_c + d, "alt": alt},
                {"lat": lat_c - d, "lon": lon_c + d, "alt": alt},
                {"lat": lat_c - d, "lon": lon_c - d, "alt": alt},
            ],
            "speed": task.params.get("speed", 8.0),
            "altitude_agl": task.params.get("altitude_agl", 35.0),
        }

    if task.type == "search_locate":
        collar_id = task.params.get("collar_id")
        target = next((p for p in latest if p["collar_id"] == collar_id), latest[0])
        alt = float(task.params.get("altitude_msl", 30.0))
        d = float(task.params.get("offset_deg", 0.0004))
        return {
            "type": "route",
            "waypoints": [
                {"lat": target["lat"], "lon": target["lon"], "alt": alt},
                {"lat": target["lat"] + d, "lon": target["lon"], "alt": alt},
                {"lat": target["lat"], "lon": target["lon"] + d, "alt": alt},
            ],
            "speed": task.params.get("speed", 7.0),
            "altitude_agl": task.params.get("altitude_agl", 30.0),
        }

    raise ValueError(f"Unsupported task type: {task.type}")
