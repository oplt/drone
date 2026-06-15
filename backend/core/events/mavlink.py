from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

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
    "EKF_STATUS_REPORT",
    "RAW_IMU",
    "SCALED_IMU2",
]


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _bounded_percent(value: float | int | None) -> int | None:
    if value is None:
        return None
    return max(0, min(100, int(round(float(value)))))


def _compact(updates: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in updates.items() if value is not None}


def _valid_lat_lon(lat: float | None, lon: float | None) -> bool:
    return (
        lat is not None
        and lon is not None
        and -90.0 <= lat <= 90.0
        and -180.0 <= lon <= 180.0
        and not (abs(lat) < 1e-12 and abs(lon) < 1e-12)
    )


def _mavlink_position(msg_dict: Mapping[str, Any]) -> dict[str, float] | None:
    lat_raw = _float_or_none(msg_dict.get("lat"))
    lon_raw = _float_or_none(msg_dict.get("lon"))
    if lat_raw is None or lon_raw is None:
        return None
    lat = lat_raw / 1e7
    lon = lon_raw / 1e7
    if not _valid_lat_lon(lat, lon):
        return None

    position = {"lat": lat, "lon": lon}
    alt = _float_or_none(msg_dict.get("alt"))
    rel_alt = _float_or_none(msg_dict.get("relative_alt"))
    if alt is not None:
        position["alt"] = alt / 1e3
    if rel_alt is not None:
        position["relative_alt"] = rel_alt / 1e3
    return position


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
    msg_type = str(msg_dict.get("mavpackettype", "") or "")
    processed: dict[str, Any] = {}
    snapshot = current_snapshot or {}

    def merge(section: str, updates: Mapping[str, Any]) -> None:
        current = dict(snapshot.get(section, {}) if isinstance(snapshot.get(section), Mapping) else {})
        current.update(_compact(updates))
        processed[section] = current

    try:
        if msg_type == "GLOBAL_POSITION_INT":
            position = _mavlink_position(msg_dict)
            if position is not None:
                processed["position"] = position

        elif msg_type == "GPS_RAW_INT":
            position = _mavlink_position(msg_dict)
            if position is not None:
                processed["position"] = position

            satellites = _int_or_none(msg_dict.get("satellites_visible"))
            hdop_raw = _int_or_none(msg_dict.get("eph"))
            hdop = None if hdop_raw in (None, 65535) else max(0.0, float(hdop_raw) / 100.0)
            fix_type = _int_or_none(msg_dict.get("fix_type"))
            merge(
                "gps",
                {
                    "fix_type": fix_type,
                    "satellites": satellites,
                    "hdop": hdop,
                },
            )

        elif msg_type == "VFR_HUD":
            heading = _float_or_none(msg_dict.get("heading"))
            if heading is not None and heading < 0:
                heading = heading % 360.0
            processed["status"] = _compact(
                {
                    "groundspeed": _float_or_none(msg_dict.get("groundspeed")),
                    "airspeed": _float_or_none(msg_dict.get("airspeed")),
                    "heading": heading,
                    "throttle": _float_or_none(msg_dict.get("throttle")),
                    "alt": _float_or_none(msg_dict.get("alt")),
                    "climb": _float_or_none(msg_dict.get("climb")),
                }
            )

        elif msg_type == "BATTERY_STATUS":
            voltages = msg_dict.get("voltages", [])
            valid_millivolts: list[float] = []
            if isinstance(voltages, (list, tuple)):
                for value in voltages:
                    mv = _float_or_none(value)
                    if mv is not None and 0 < mv < 65535:
                        valid_millivolts.append(mv)
            voltage = sum(valid_millivolts) / 1000.0 if valid_millivolts else None

            current_raw = _float_or_none(msg_dict.get("current_battery"))
            current = None if current_raw is None or current_raw < 0 else current_raw / 100.0

            remaining = _int_or_none(msg_dict.get("battery_remaining"))
            if remaining is not None and remaining < 0:
                remaining = None

            temperature_raw = _float_or_none(msg_dict.get("temperature"))
            temperature = (
                None
                if temperature_raw is None or int(temperature_raw) == 32767
                else temperature_raw / 100.0
            )

            merge(
                "battery",
                {
                    "voltage": voltage,
                    "current": current,
                    "remaining": remaining,
                    "temperature": temperature,
                },
            )

        elif msg_type == "ATTITUDE":
            processed["attitude"] = _compact(
                {
                    "roll": _float_or_none(msg_dict.get("roll")),
                    "pitch": _float_or_none(msg_dict.get("pitch")),
                    "yaw": _float_or_none(msg_dict.get("yaw")),
                    "rollspeed": _float_or_none(msg_dict.get("rollspeed")),
                    "pitchspeed": _float_or_none(msg_dict.get("pitchspeed")),
                    "yawspeed": _float_or_none(msg_dict.get("yawspeed")),
                }
            )

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
            custom_mode = _int_or_none(msg_dict.get("custom_mode")) or 0
            processed["mode"] = mode_mapping.get(custom_mode, "UNKNOWN")
            base_mode = _int_or_none(msg_dict.get("base_mode")) or 0
            processed["armed"] = bool(base_mode & 0x80)

            system_status = _int_or_none(msg_dict.get("system_status"))
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
                status_label = status_map.get(system_status, "UNKNOWN")
                merge("system", {"status": status_label})
                if status_label in {"CRITICAL", "EMERGENCY", "FLIGHT_TERMINATION"}:
                    merge("failsafe", {"state": status_label})
            merge("heartbeat", {"last_received": datetime.now(UTC).isoformat()})

        elif msg_type == "SYS_STATUS":
            drop_rate = _float_or_none(msg_dict.get("drop_rate_comm"))
            telemetry_quality = None
            if drop_rate is not None:
                # MAVLink drop_rate_comm is centi-percent.
                telemetry_quality = _bounded_percent(100.0 - (drop_rate / 100.0))
            merge("link", {"telemetry": telemetry_quality})

            battery_remaining = _int_or_none(msg_dict.get("battery_remaining"))
            if battery_remaining is not None and battery_remaining >= 0:
                merge("battery", {"remaining": battery_remaining})

        elif msg_type == "RADIO_STATUS":
            rssi = _int_or_none(msg_dict.get("rssi"))
            remrssi = _int_or_none(msg_dict.get("remrssi"))
            rc_quality = _bounded_percent((rssi / 255.0) * 100.0) if rssi is not None else None
            telem_quality = (
                _bounded_percent((remrssi / 255.0) * 100.0) if remrssi is not None else None
            )
            merge("link", {"rc": rc_quality, "telemetry": telem_quality})

        elif msg_type == "RC_CHANNELS":
            rssi = _int_or_none(msg_dict.get("rssi"))
            if rssi is not None:
                merge("link", {"rc": _bounded_percent((rssi / 255.0) * 100.0)})

        elif msg_type == "WIND":
            speed = _float_or_none(msg_dict.get("speed"))
            direction = _float_or_none(msg_dict.get("direction"))
            if speed is not None or direction is not None:
                merge("wind", {"speed": speed, "direction": direction})

        elif msg_type == "STATUSTEXT":
            text = str(msg_dict.get("text", "") or "").strip()
            if text:
                lowered = text.lower()
                if "failsafe" in lowered or "emergency" in lowered:
                    merge("failsafe", {"state": text[:64]})

        elif msg_type == "EKF_STATUS_REPORT":
            flags = _int_or_none(msg_dict.get("flags")) or 0
            velocity_ok = bool(flags & 0x01)
            pos_horiz_ok = bool(flags & 0x02)
            pos_vert_ok = bool(flags & 0x04)
            compass_ok = bool(flags & 0x08)
            merge(
                "ekf",
                {
                    "flags": flags,
                    "velocity_ok": velocity_ok,
                    "pos_horiz_ok": pos_horiz_ok,
                    "pos_vert_ok": pos_vert_ok,
                    "compass_ok": compass_ok,
                    "ok": velocity_ok and pos_horiz_ok and pos_vert_ok,
                    "velocity_variance": _float_or_none(msg_dict.get("velocity_variance")),
                    "pos_horiz_variance": _float_or_none(msg_dict.get("pos_horiz_variance")),
                    "pos_vert_variance": _float_or_none(msg_dict.get("pos_vert_variance")),
                    "compass_variance": _float_or_none(msg_dict.get("compass_variance")),
                },
            )

        elif msg_type in ("RAW_IMU", "SCALED_IMU2"):
            xmag = _float_or_none(msg_dict.get("xmag")) or 0.0
            ymag = _float_or_none(msg_dict.get("ymag")) or 0.0
            zmag = _float_or_none(msg_dict.get("zmag")) or 0.0
            mag_field = math.sqrt(xmag * xmag + ymag * ymag + zmag * zmag)
            healthy = 100 < mag_field < 800
            merge(
                "compass",
                {
                    "x": xmag,
                    "y": ymag,
                    "z": zmag,
                    "mag_field": round(mag_field, 1),
                    "healthy": healthy,
                },
            )

    except Exception:
        # Preserve backward-compatible "best effort" behavior.
        return processed

    return processed


def raw_event_from_mavlink_message(
    msg_dict: Mapping[str, Any],
    *,
    flight_id: int | None,
    timestamp_s: float,
) -> dict[str, Any]:
    payload = dict(msg_dict)
    timestamp = _float_or_none(timestamp_s)
    if timestamp is None or timestamp < 0:
        timestamp = datetime.now(UTC).timestamp()
    payload["timestamp"] = timestamp

    time_unix_usec_raw = payload.get("time_unix_usec")
    time_unix_usec = None
    if time_unix_usec_raw:
        parsed = _float_or_none(time_unix_usec_raw)
        if parsed is not None and parsed > 0:
            try:
                time_unix_usec = datetime.fromtimestamp(parsed / 1_000_000, tz=UTC)
            except (OverflowError, OSError, ValueError):
                time_unix_usec = None

    return {
        "flight_id": flight_id,
        "msg_type": payload.get("mavpackettype"),
        "time_boot_ms": payload.get("time_boot_ms"),
        "time_unix_usec": time_unix_usec,
        "timestamp": datetime.fromtimestamp(timestamp, tz=UTC),
        "payload": payload,
    }
