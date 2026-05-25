from __future__ import annotations

import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

RuntimeEnvelopeKind = Literal[
    "telemetry",
    "flight_event",
    "video_health",
    "alert_event",
    "mission_lifecycle",
]
AlertEventActionV1 = Literal["created", "updated", "acknowledged", "resolved"]
AlertSeverityV1 = Literal["info", "medium", "high", "critical"]
AlertStatusV1 = Literal["open", "acknowledged", "resolved"]
MissionLifecycleStateV1 = Literal[
    "queued",
    "running",
    "paused",
    "aborted",
    "completed",
    "failed",
]

_SEQUENCE_LOCK = threading.Lock()
_SEQUENCE_COUNTERS: dict[str, int] = {}


def utc_now() -> datetime:
    return datetime.now(UTC)


def next_runtime_sequence(mission_runtime_id: str | None, source: str) -> int:
    key = mission_runtime_id or f"producer:{source}"
    with _SEQUENCE_LOCK:
        current = _SEQUENCE_COUNTERS.get(key, 0) + 1
        _SEQUENCE_COUNTERS[key] = current
        return current


def _event_id() -> str:
    return str(uuid4())


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


class MissionContextV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mission_name: str | None = None
    mission_type: str | None = None
    mission_task_type: str | None = None
    preflight_run_id: str | None = None


def mission_context_from_runtime(runtime: Any | None) -> MissionContextV1 | None:
    if runtime is None:
        return None
    mission_task_type = getattr(runtime, "mission_task_type", None) or getattr(
        runtime, "private_patrol_task_type", None
    )
    context = MissionContextV1(
        mission_name=getattr(runtime, "mission_name", None),
        mission_type=getattr(runtime, "mission_type", None),
        mission_task_type=mission_task_type,
        preflight_run_id=getattr(runtime, "preflight_run_id", None),
    )
    return context if any(context.model_dump().values()) else None


class RuntimeEnvelopeBaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["runtime-envelope.v1"] = Field(
        default="runtime-envelope.v1",
        validation_alias=AliasChoices("schema", "schema_version"),
        serialization_alias="schema",
    )
    kind: RuntimeEnvelopeKind
    event_id: str = Field(default_factory=_event_id)
    mission_runtime_id: str | None = None
    db_flight_id: int | None = None
    sequence: int
    emitted_at: datetime = Field(default_factory=utc_now)
    source: str
    mission: MissionContextV1 | None = None
    payload: Any

    def model_dump_jsonable(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True, by_alias=True)


class TelemetryPositionV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    relative_alt_m: float | None = None


class TelemetryAttitudeV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    roll_rad: float | None = None
    pitch_rad: float | None = None
    yaw_rad: float | None = None
    roll_rate_rad_s: float | None = None
    pitch_rate_rad_s: float | None = None
    yaw_rate_rad_s: float | None = None


class TelemetryBatteryV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    voltage_v: float | None = None
    current_a: float | None = None
    remaining_pct: int | None = None
    temperature_c: float | None = None


class TelemetryGpsV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fix_type: int | None = None
    satellites_visible: int | None = None
    hdop: float | None = None


class TelemetryLinkV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rc_quality_pct: int | None = None
    telemetry_quality_pct: int | None = None
    lte_quality_pct: int | None = None


class TelemetryWindV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    speed_mps: float | None = None
    direction_deg: float | None = None


class TelemetryMotionV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    groundspeed_mps: float | None = None
    airspeed_mps: float | None = None
    heading_deg: float | None = None
    throttle_pct: float | None = None
    climb_mps: float | None = None


class TelemetrySystemV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str | None = None


class TelemetryFailsafeV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: str | None = None


class TelemetryHeartbeatV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    last_received: str | None = None


class TelemetryEkfV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    flags: int | None = None
    ok: bool | None = None
    velocity_ok: bool | None = None
    pos_horiz_ok: bool | None = None
    pos_vert_ok: bool | None = None
    compass_ok: bool | None = None
    velocity_variance: float | None = None
    pos_horiz_variance: float | None = None
    pos_vert_variance: float | None = None
    compass_variance: float | None = None


class TelemetryCompassV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x: float | None = None
    y: float | None = None
    z: float | None = None
    mag_field: float | None = None
    healthy: bool | None = None


class TelemetryCameraV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gimbal_pitch_deg: float | None = None


class TelemetryPayloadV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    position: TelemetryPositionV1 = Field(default_factory=TelemetryPositionV1)
    attitude: TelemetryAttitudeV1 = Field(default_factory=TelemetryAttitudeV1)
    battery: TelemetryBatteryV1 = Field(default_factory=TelemetryBatteryV1)
    gps: TelemetryGpsV1 = Field(default_factory=TelemetryGpsV1)
    link: TelemetryLinkV1 = Field(default_factory=TelemetryLinkV1)
    wind: TelemetryWindV1 = Field(default_factory=TelemetryWindV1)
    motion: TelemetryMotionV1 = Field(default_factory=TelemetryMotionV1)
    system: TelemetrySystemV1 = Field(default_factory=TelemetrySystemV1)
    failsafe: TelemetryFailsafeV1 = Field(default_factory=TelemetryFailsafeV1)
    camera: TelemetryCameraV1 = Field(default_factory=TelemetryCameraV1)
    heartbeat: TelemetryHeartbeatV1 = Field(default_factory=TelemetryHeartbeatV1)
    ekf: TelemetryEkfV1 = Field(default_factory=TelemetryEkfV1)
    compass: TelemetryCompassV1 = Field(default_factory=TelemetryCompassV1)
    flight_mode: str = "DISCONNECTED"
    armed: bool = False
    coalesced_message_count: int | None = None

    @classmethod
    def from_legacy_snapshot(
        cls,
        snapshot: Mapping[str, Any] | None,
        *,
        coalesced_message_count: int | None = None,
    ) -> TelemetryPayloadV1:
        snap = dict(snapshot or {})
        position = snap.get("position") or {}
        attitude = snap.get("attitude") or {}
        battery = snap.get("battery") or {}
        gps = snap.get("gps") or {}
        link = snap.get("link") or {}
        wind = snap.get("wind") or {}
        motion = snap.get("status") or snap.get("motion") or {}
        system = snap.get("system") or {}
        failsafe = snap.get("failsafe") or {}
        camera = snap.get("camera") or {}
        heartbeat_data = snap.get("heartbeat") or {}
        ekf_data = snap.get("ekf") or {}
        compass_data = snap.get("compass") or {}

        return cls(
            position=TelemetryPositionV1(
                lat=_float_or_none(position.get("lat")),
                lon=_float_or_none(position.get("lon")),
                alt_m=_float_or_none(position.get("alt_m", position.get("alt"))),
                relative_alt_m=_float_or_none(
                    position.get("relative_alt_m", position.get("relative_alt"))
                ),
            ),
            attitude=TelemetryAttitudeV1(
                roll_rad=_float_or_none(attitude.get("roll_rad", attitude.get("roll"))),
                pitch_rad=_float_or_none(attitude.get("pitch_rad", attitude.get("pitch"))),
                yaw_rad=_float_or_none(attitude.get("yaw_rad", attitude.get("yaw"))),
                roll_rate_rad_s=_float_or_none(
                    attitude.get("roll_rate_rad_s", attitude.get("rollspeed"))
                ),
                pitch_rate_rad_s=_float_or_none(
                    attitude.get("pitch_rate_rad_s", attitude.get("pitchspeed"))
                ),
                yaw_rate_rad_s=_float_or_none(
                    attitude.get("yaw_rate_rad_s", attitude.get("yawspeed"))
                ),
            ),
            battery=TelemetryBatteryV1(
                voltage_v=_float_or_none(battery.get("voltage_v", battery.get("voltage"))),
                current_a=_float_or_none(battery.get("current_a", battery.get("current"))),
                remaining_pct=_int_or_none(battery.get("remaining_pct", battery.get("remaining"))),
                temperature_c=_float_or_none(
                    battery.get("temperature_c", battery.get("temperature"))
                ),
            ),
            gps=TelemetryGpsV1(
                fix_type=_int_or_none(gps.get("fix_type")),
                satellites_visible=_int_or_none(
                    gps.get("satellites_visible", gps.get("satellites"))
                ),
                hdop=_float_or_none(gps.get("hdop")),
            ),
            link=TelemetryLinkV1(
                rc_quality_pct=_int_or_none(link.get("rc_quality_pct", link.get("rc"))),
                telemetry_quality_pct=_int_or_none(
                    link.get("telemetry_quality_pct", link.get("telemetry"))
                ),
                lte_quality_pct=_int_or_none(link.get("lte_quality_pct", link.get("lte"))),
            ),
            wind=TelemetryWindV1(
                speed_mps=_float_or_none(wind.get("speed_mps", wind.get("speed"))),
                direction_deg=_float_or_none(wind.get("direction_deg", wind.get("direction"))),
            ),
            motion=TelemetryMotionV1(
                groundspeed_mps=_float_or_none(
                    motion.get("groundspeed_mps", motion.get("groundspeed"))
                ),
                airspeed_mps=_float_or_none(motion.get("airspeed_mps", motion.get("airspeed"))),
                heading_deg=_float_or_none(motion.get("heading_deg", motion.get("heading"))),
                throttle_pct=_float_or_none(motion.get("throttle_pct", motion.get("throttle"))),
                climb_mps=_float_or_none(motion.get("climb_mps", motion.get("climb"))),
            ),
            system=TelemetrySystemV1(status=system.get("status")),
            failsafe=TelemetryFailsafeV1(state=failsafe.get("state")),
            camera=TelemetryCameraV1(
                gimbal_pitch_deg=_float_or_none(camera.get("gimbal_pitch_deg"))
            ),
            heartbeat=TelemetryHeartbeatV1(
                last_received=heartbeat_data.get("last_received"),
            ),
            ekf=TelemetryEkfV1(
                **{k: ekf_data[k] for k in ekf_data if k in TelemetryEkfV1.model_fields}
            ),
            compass=TelemetryCompassV1(
                **{k: compass_data[k] for k in compass_data if k in TelemetryCompassV1.model_fields}
            ),
            flight_mode=str(snap.get("flight_mode", snap.get("mode", "DISCONNECTED"))),
            armed=bool(snap.get("armed", False)),
            coalesced_message_count=coalesced_message_count,
        )

    def has_position(self) -> bool:
        lat = self.position.lat
        lon = self.position.lon
        return (
            lat is not None
            and lon is not None
            and -90.0 <= lat <= 90.0
            and -180.0 <= lon <= 180.0
            and not (abs(lat) < 1e-8 and abs(lon) < 1e-8)
        )

    def to_legacy_snapshot(self, *, timestamp_s: float | None = None) -> dict[str, Any]:
        return {
            "position": {
                "lat": self.position.lat or 0,
                "lon": self.position.lon or 0,
                "alt": self.position.alt_m or 0,
                "relative_alt": self.position.relative_alt_m or 0,
            },
            "attitude": {
                "roll": self.attitude.roll_rad or 0,
                "pitch": self.attitude.pitch_rad or 0,
                "yaw": self.attitude.yaw_rad or 0,
                "rollspeed": self.attitude.roll_rate_rad_s or 0,
                "pitchspeed": self.attitude.pitch_rate_rad_s or 0,
                "yawspeed": self.attitude.yaw_rate_rad_s or 0,
            },
            "battery": {
                "voltage": self.battery.voltage_v or 0,
                "current": self.battery.current_a or 0,
                "remaining": self.battery.remaining_pct or 0,
                "temperature": self.battery.temperature_c or 0,
            },
            "gps": {
                "fix_type": self.gps.fix_type,
                "satellites": self.gps.satellites_visible or 0,
                "hdop": self.gps.hdop,
            },
            "link": {
                "rc": self.link.rc_quality_pct,
                "lte": self.link.lte_quality_pct,
                "telemetry": self.link.telemetry_quality_pct,
            },
            "wind": {
                "speed": self.wind.speed_mps or 0,
                "direction": self.wind.direction_deg or 0,
            },
            "failsafe": {"state": self.failsafe.state or "Normal"},
            "system": {"status": self.system.status or "UNKNOWN"},
            "status": {
                "groundspeed": self.motion.groundspeed_mps or 0,
                "airspeed": self.motion.airspeed_mps or 0,
                "heading": self.motion.heading_deg or 0,
                "throttle": self.motion.throttle_pct or 0,
                "climb": self.motion.climb_mps or 0,
            },
            "camera": {
                "gimbal_pitch_deg": self.camera.gimbal_pitch_deg,
            },
            "heartbeat": {
                "last_received": self.heartbeat.last_received,
            },
            "ekf": {
                "flags": self.ekf.flags,
                "ok": self.ekf.ok,
                "velocity_ok": self.ekf.velocity_ok,
                "pos_horiz_ok": self.ekf.pos_horiz_ok,
                "pos_vert_ok": self.ekf.pos_vert_ok,
                "compass_ok": self.ekf.compass_ok,
                "velocity_variance": self.ekf.velocity_variance,
                "pos_horiz_variance": self.ekf.pos_horiz_variance,
                "pos_vert_variance": self.ekf.pos_vert_variance,
                "compass_variance": self.ekf.compass_variance,
            },
            "compass": {
                "x": self.compass.x,
                "y": self.compass.y,
                "z": self.compass.z,
                "mag_field": self.compass.mag_field,
                "healthy": self.compass.healthy,
            },
            "mode": self.flight_mode,
            "armed": self.armed,
            "timestamp": timestamp_s or 0,
        }


class TelemetryEnvelopeV1(RuntimeEnvelopeBaseV1):
    kind: Literal["telemetry"] = "telemetry"
    payload: TelemetryPayloadV1

    def to_legacy_websocket_message(self) -> dict[str, Any]:
        return {
            "type": "telemetry",
            "data": self.payload.to_legacy_snapshot(
                timestamp_s=self.emitted_at.timestamp(),
            ),
        }


class FlightEventSeverityV1(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FlightEventPayloadV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_name: str
    category: str | None = None
    severity: FlightEventSeverityV1 | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class FlightEventEnvelopeV1(RuntimeEnvelopeBaseV1):
    kind: Literal["flight_event"] = "flight_event"
    payload: FlightEventPayloadV1


class VideoHealthPayloadV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stream_started: bool
    healthy: bool
    frame_count: int
    fps: float | None = None
    resolution: str | None = None
    source: str | None = None
    recording_active: bool
    recording_file: str | None = None
    recording_path: str | None = None
    error: str | None = None

    @classmethod
    def from_status(cls, status: Mapping[str, Any] | None) -> VideoHealthPayloadV1:
        raw = dict(status or {})
        source = raw.get("source")
        return cls(
            stream_started=bool(raw.get("stream_started", raw.get("started", False))),
            healthy=bool(raw.get("healthy", False)),
            frame_count=_int_or_none(raw.get("frame_count")) or 0,
            fps=_float_or_none(raw.get("fps")),
            resolution=(
                str(raw.get("resolution")) if raw.get("resolution") not in (None, "") else None
            ),
            source=str(source) if source not in (None, "") else None,
            recording_active=bool(raw.get("recording_active", raw.get("recording", False))),
            recording_file=raw.get("recording_file"),
            recording_path=raw.get("recording_path"),
            error=raw.get("error"),
        )

    def to_legacy_status_payload(self, *, timestamp_s: float) -> dict[str, Any]:
        return {
            "timestamp": timestamp_s,
            "healthy": self.healthy,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "resolution": self.resolution,
            "recording": self.recording_active,
            "recording_file": self.recording_file,
        }


class VideoHealthEnvelopeV1(RuntimeEnvelopeBaseV1):
    kind: Literal["video_health"] = "video_health"
    payload: VideoHealthPayloadV1


class AlertSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alert_id: int
    rule_type: str
    dedupe_key: str
    source: str
    severity: AlertSeverityV1
    status: AlertStatusV1
    title: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    first_triggered_at: datetime
    last_triggered_at: datetime
    last_notified_at: datetime | None = None
    resolved_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by_user_id: int | None = None
    occurrences: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_alert(cls, alert: Any) -> AlertSnapshotV1:
        from backend.modules.alerts.schemas import OperationalAlertOut

        if isinstance(alert, BaseModel):
            raw = alert.model_dump(mode="python")
        elif isinstance(alert, Mapping):
            raw = dict(alert)
        else:
            raw = OperationalAlertOut.model_validate(alert).model_dump(mode="python")

        return cls(
            alert_id=int(raw.get("alert_id", raw.get("id"))),
            rule_type=str(raw.get("rule_type")),
            dedupe_key=str(raw.get("dedupe_key")),
            source=str(raw.get("source")),
            severity=raw.get("severity"),
            status=raw.get("status"),
            title=str(raw.get("title")),
            message=str(raw.get("message")),
            metadata=dict(raw.get("metadata", raw.get("meta_data", {})) or {}),
            first_triggered_at=raw.get("first_triggered_at"),
            last_triggered_at=raw.get("last_triggered_at"),
            last_notified_at=raw.get("last_notified_at"),
            resolved_at=raw.get("resolved_at"),
            acknowledged_at=raw.get("acknowledged_at"),
            acknowledged_by_user_id=raw.get("acknowledged_by_user_id"),
            occurrences=int(raw.get("occurrences", 0)),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
        )

    def to_legacy_alert_dict(self) -> dict[str, Any]:
        return {
            "id": self.alert_id,
            "rule_type": self.rule_type,
            "dedupe_key": self.dedupe_key,
            "source": self.source,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "meta_data": self.metadata,
            "first_triggered_at": self.first_triggered_at.isoformat(),
            "last_triggered_at": self.last_triggered_at.isoformat(),
            "last_notified_at": (
                self.last_notified_at.isoformat() if self.last_notified_at else None
            ),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": (self.acknowledged_at.isoformat() if self.acknowledged_at else None),
            "acknowledged_by_user_id": self.acknowledged_by_user_id,
            "occurrences": self.occurrences,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AlertEventPayloadV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: AlertEventActionV1
    alert: AlertSnapshotV1


class AlertEventEnvelopeV1(RuntimeEnvelopeBaseV1):
    kind: Literal["alert_event"] = "alert_event"
    payload: AlertEventPayloadV1

    def to_legacy_websocket_message(self) -> dict[str, Any]:
        return {
            "type": "alert_event",
            "action": self.payload.action,
            "alert": self.payload.alert.to_legacy_alert_dict(),
        }


class MissionLifecyclePayloadV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: MissionLifecycleStateV1
    previous_state: MissionLifecycleStateV1 | None = None
    trigger: str
    reason: str | None = None
    error: str | None = None
    command_id: str | None = None
    requested_by_user_id: int | None = None


class MissionLifecycleEnvelopeV1(RuntimeEnvelopeBaseV1):
    kind: Literal["mission_lifecycle"] = "mission_lifecycle"
    payload: MissionLifecyclePayloadV1
