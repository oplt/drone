from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


TELEMETRY_MAVLINK_TYPES: list[str] = [
    "GLOBAL_POSITION_INT",
    "VFR_HUD",
    "BATTERY_STATUS",
    "ATTITUDE",
    "HEARTBEAT",
    "GPS_RAW_INT",
    "SYS_STATUS",
    "RADIO_STATUS",
    "RC_CHANNELS",
    "WIND",
    "STATUSTEXT",
]


def check_mavlink_connection(mav_conn: Any) -> bool:
    try:
        msg = mav_conn.recv_match(blocking=False, timeout=0.1)
        return msg is not None
    except Exception:
        return False


def process_mavlink_message(
    msg_dict: Mapping[str, Any],
    *,
    current_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    msg_type = msg_dict.get("mavpackettype", "")
    processed: dict[str, Any] = {}
    snapshot = current_snapshot or {}

    def merge(section: str, updates: dict[str, Any]) -> None:
        current = dict(snapshot.get(section, {}))
        current.update(updates)
        processed[section] = current

    try:
        if msg_type == "GLOBAL_POSITION_INT":
            lat = msg_dict.get("lat", 0)
            lon = msg_dict.get("lon", 0)
            if lat != 0 or lon != 0:
                processed["position"] = {
                    "lat": float(lat) / 1e7,
                    "lon": float(lon) / 1e7,
                    "alt": float(msg_dict.get("alt", 0)) / 1e3,
                    "relative_alt": float(msg_dict.get("relative_alt", 0)) / 1e3,
                }

        elif msg_type == "GPS_RAW_INT":
            lat = msg_dict.get("lat", 0)
            lon = msg_dict.get("lon", 0)
            if lat != 0 or lon != 0:
                processed["position"] = {
                    "lat": float(lat) / 1e7,
                    "lon": float(lon) / 1e7,
                    "alt": float(msg_dict.get("alt", 0)) / 1e3,
                }
            satellites = msg_dict.get("satellites_visible")
            hdop_raw = msg_dict.get("eph")
            hdop = None
            if hdop_raw not in (None, 65535):
                try:
                    hdop = float(hdop_raw) / 100.0
                except Exception:
                    hdop = None
            merge(
                "gps",
                {
                    "satellites": int(satellites)
                    if satellites is not None
                    else snapshot.get("gps", {}).get("satellites", 0),
                    "hdop": hdop,
                },
            )

        elif msg_type == "VFR_HUD":
            processed["status"] = {
                "groundspeed": float(msg_dict.get("groundspeed", 0)),
                "airspeed": float(msg_dict.get("airspeed", 0)),
                "heading": float(msg_dict.get("heading", 0)),
                "throttle": float(msg_dict.get("throttle", 0)),
                "alt": float(msg_dict.get("alt", 0)),
                "climb": float(msg_dict.get("climb", 0)),
            }

        elif msg_type == "BATTERY_STATUS":
            voltages = msg_dict.get("voltages", [0])
            voltage = (
                float(voltages[0]) / 1000 if voltages and voltages[0] > 0 else 0.0
            )
            merge(
                "battery",
                {
                    "voltage": voltage,
                    "current": float(msg_dict.get("current_battery", 0)) / 100,
                    "remaining": int(msg_dict.get("battery_remaining", -1)),
                    "temperature": float(msg_dict.get("temperature", 0)),
                },
            )

        elif msg_type == "ATTITUDE":
            processed["attitude"] = {
                "roll": float(msg_dict.get("roll", 0)),
                "pitch": float(msg_dict.get("pitch", 0)),
                "yaw": float(msg_dict.get("yaw", 0)),
                "rollspeed": float(msg_dict.get("rollspeed", 0)),
                "pitchspeed": float(msg_dict.get("pitchspeed", 0)),
                "yawspeed": float(msg_dict.get("yawspeed", 0)),
            }

        elif msg_type == "HEARTBEAT":
            mode_mapping = {
                0: "STABILIZE",
                1: "ACRO",
                2: "ALT_HOLD",
                3: "AUTO",
                4: "GUIDED",
                5: "LOITER",
                6: "RTL",
                7: "CIRCLE",
                8: "POSITION",
                9: "LAND",
                10: "OF_LOITER",
                11: "DRIFT",
                13: "SPORT",
                14: "FLIP",
                15: "AUTOTUNE",
                16: "POSHOLD",
                17: "BRAKE",
                18: "THROW",
                19: "AVOID_ADSB",
                20: "GUIDED_NOGPS",
                21: "SMART_RTL",
            }
            custom_mode = msg_dict.get("custom_mode", 0)
            processed["mode"] = mode_mapping.get(custom_mode, "UNKNOWN")
            processed["armed"] = bool(msg_dict.get("base_mode", 0) & 0x80)
            system_status = msg_dict.get("system_status")
            status_map = {
                0: "UNINIT",
                1: "BOOT",
                2: "CALIBRATING",
                3: "STANDBY",
                4: "ACTIVE",
                5: "CRITICAL",
                6: "EMERGENCY",
                7: "POWEROFF",
                8: "FLIGHT_TERMINATION",
            }
            if system_status is not None:
                status_label = status_map.get(int(system_status), "UNKNOWN")
                merge("system", {"status": status_label})
                if status_label in {"CRITICAL", "EMERGENCY", "FLIGHT_TERMINATION"}:
                    merge("failsafe", {"state": status_label})

        elif msg_type == "SYS_STATUS":
            drop_rate = msg_dict.get("drop_rate_comm")
            if drop_rate is not None:
                try:
                    telemetry_quality = max(0, 100 - int(drop_rate))
                except Exception:
                    telemetry_quality = None
                merge("link", {"telemetry": telemetry_quality})

            battery_remaining = msg_dict.get("battery_remaining")
            if battery_remaining is not None:
                merge("battery", {"remaining": int(battery_remaining)})

        elif msg_type == "RADIO_STATUS":
            rssi = msg_dict.get("rssi")
            remrssi = msg_dict.get("remrssi")
            rc_quality = None
            telem_quality = None
            if rssi is not None:
                rc_quality = min(100, round((int(rssi) / 255) * 100))
            if remrssi is not None:
                telem_quality = min(100, round((int(remrssi) / 255) * 100))
            merge("link", {"rc": rc_quality, "telemetry": telem_quality})

        elif msg_type == "RC_CHANNELS":
            rssi = msg_dict.get("rssi")
            if rssi is not None:
                rc_quality = min(100, round((int(rssi) / 255) * 100))
                merge("link", {"rc": rc_quality})

        elif msg_type == "WIND":
            speed = msg_dict.get("speed")
            direction = msg_dict.get("direction")
            if speed is not None or direction is not None:
                merge(
                    "wind",
                    {
                        "speed": float(speed) if speed is not None else 0,
                        "direction": float(direction) if direction is not None else 0,
                    },
                )

        elif msg_type == "STATUSTEXT":
            text = str(msg_dict.get("text", "")).strip()
            if text:
                lowered = text.lower()
                if "failsafe" in lowered or "emergency" in lowered:
                    merge("failsafe", {"state": text[:64]})

    except Exception:
        return processed

    return processed


def raw_event_from_mavlink_message(
    msg_dict: Mapping[str, Any],
    *,
    flight_id: int | None,
    timestamp_s: float,
) -> dict[str, Any]:
    payload = dict(msg_dict)
    payload["timestamp"] = timestamp_s

    time_unix_usec_raw = payload.get("time_unix_usec")
    time_unix_usec = None
    if time_unix_usec_raw:
        try:
            time_unix_usec = datetime.fromtimestamp(
                float(time_unix_usec_raw) / 1_000_000,
                tz=timezone.utc,
            )
        except Exception:
            time_unix_usec = None

    return {
        "flight_id": flight_id,
        "msg_type": payload.get("mavpackettype"),
        "time_boot_ms": payload.get("time_boot_ms"),
        "time_unix_usec": time_unix_usec,
        "timestamp": datetime.fromtimestamp(timestamp_s, tz=timezone.utc),
        "payload": payload,
    }
