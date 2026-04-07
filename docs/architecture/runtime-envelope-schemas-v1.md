# Runtime Envelope Schemas V1

## Status
Accepted schema spec

## Date
2026-03-31

## Purpose

This document defines the canonical runtime envelope schemas that the live-ops
runtime will emit after the bus refactor. It is the normative schema reference
for the next implementation step that adds typed backend models.

This spec covers:

- telemetry envelopes
- flight event envelopes
- video health envelopes
- alert event envelopes
- mission lifecycle envelopes

This spec does not yet cover ML-specific anomaly envelopes. Those remain outside
the canonical runtime contract for now.

## Core Decisions

### One outer envelope

Every runtime message uses the same outer structure and varies only by `kind`
and `payload`.

### One canonical runtime identifier

- `mission_runtime_id`
  - canonical runtime identifier
  - maps to the current `client_flight_id`
- `db_flight_id`
  - optional integer `flights.id`
  - null until a durable flight record exists

### One timestamp convention

- All timestamps are UTC ISO-8601 datetimes in serialized form.
- Epoch floats are not part of the canonical schema.

### One sequencing rule

- `sequence` is monotonic per `mission_runtime_id`.
- If no mission runtime exists yet, `sequence` is monotonic per process-local
  producer stream until a mission runtime is assigned.

### One source naming rule

- `source` is a dot-qualified producer name.
- Examples:
  - `orchestrator.telemetry`
  - `orchestrator.lifecycle`
  - `orchestrator.video`
  - `alerts.engine`
  - `alerts.api`
  - `mission.grid`
  - `mission.photogrammetry`

## Outer Envelope

### Canonical model

```python
RuntimeEnvelopeKind = Literal[
    "telemetry",
    "flight_event",
    "video_health",
    "alert_event",
    "mission_lifecycle",
]

class MissionContextV1(BaseModel):
    mission_name: str | None = None
    mission_type: str | None = None
    mission_task_type: str | None = None
    preflight_run_id: str | None = None

class RuntimeEnvelopeBaseV1(BaseModel):
    schema: Literal["runtime-envelope.v1"]
    kind: RuntimeEnvelopeKind
    event_id: str
    mission_runtime_id: str | None = None
    db_flight_id: int | None = None
    sequence: int
    emitted_at: datetime
    source: str
    mission: MissionContextV1 | None = None
    payload: Any
```

### Field rules

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `schema` | literal | yes | Always `runtime-envelope.v1` |
| `kind` | enum | yes | One of the five canonical runtime kinds |
| `event_id` | string | yes | Opaque unique event id; UUID4 string is acceptable |
| `mission_runtime_id` | string or null | no | Canonical runtime id; current `client_flight_id` |
| `db_flight_id` | int or null | no | Current `flights.id` |
| `sequence` | int | yes | Monotonic within a runtime stream |
| `emitted_at` | datetime | yes | UTC event emission time |
| `source` | string | yes | Dot-qualified producer name |
| `mission` | object or null | no | Mission context snapshot |
| `payload` | typed object | yes | Schema varies by `kind` |

## Telemetry Envelope

### Canonical model

```python
class TelemetryPositionV1(BaseModel):
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    relative_alt_m: float | None = None

class TelemetryAttitudeV1(BaseModel):
    roll_rad: float | None = None
    pitch_rad: float | None = None
    yaw_rad: float | None = None
    roll_rate_rad_s: float | None = None
    pitch_rate_rad_s: float | None = None
    yaw_rate_rad_s: float | None = None

class TelemetryBatteryV1(BaseModel):
    voltage_v: float | None = None
    current_a: float | None = None
    remaining_pct: int | None = None
    temperature_c: float | None = None

class TelemetryGpsV1(BaseModel):
    satellites_visible: int | None = None
    hdop: float | None = None

class TelemetryLinkV1(BaseModel):
    rc_quality_pct: int | None = None
    telemetry_quality_pct: int | None = None
    lte_quality_pct: int | None = None

class TelemetryWindV1(BaseModel):
    speed_mps: float | None = None
    direction_deg: float | None = None

class TelemetryMotionV1(BaseModel):
    groundspeed_mps: float | None = None
    airspeed_mps: float | None = None
    heading_deg: float | None = None
    throttle_pct: float | None = None
    climb_mps: float | None = None

class TelemetrySystemV1(BaseModel):
    status: str | None = None

class TelemetryFailsafeV1(BaseModel):
    state: str | None = None

class TelemetryCameraV1(BaseModel):
    gimbal_pitch_deg: float | None = None

class TelemetryPayloadV1(BaseModel):
    position: TelemetryPositionV1
    attitude: TelemetryAttitudeV1
    battery: TelemetryBatteryV1
    gps: TelemetryGpsV1
    link: TelemetryLinkV1
    wind: TelemetryWindV1
    motion: TelemetryMotionV1
    system: TelemetrySystemV1
    failsafe: TelemetryFailsafeV1
    camera: TelemetryCameraV1
    flight_mode: str
    armed: bool
    coalesced_message_count: int | None = None
```

### Decision notes

- Telemetry is a normalized snapshot, not a raw packet.
- This payload is the canonical replacement for the current
  `telemetry_manager.last_telemetry` shape.
- The current websocket `status` section is renamed to `motion`.
- The current top-level `mode` field is renamed to `flight_mode`.
- Camera is included even though it is sparse today, because the ML pipeline
  already looks for camera/gimbal context.

### Mapping from current shape

| Current field | Canonical field |
| --- | --- |
| `position.alt` | `position.alt_m` |
| `position.relative_alt` | `position.relative_alt_m` |
| `battery.voltage` | `battery.voltage_v` |
| `battery.current` | `battery.current_a` |
| `battery.remaining` | `battery.remaining_pct` |
| `link.rc` | `link.rc_quality_pct` |
| `link.telemetry` | `link.telemetry_quality_pct` |
| `wind.speed` | `wind.speed_mps` |
| `wind.direction` | `wind.direction_deg` |
| `status.groundspeed` | `motion.groundspeed_mps` |
| `status.airspeed` | `motion.airspeed_mps` |
| `status.heading` | `motion.heading_deg` |
| `status.throttle` | `motion.throttle_pct` |
| `status.climb` | `motion.climb_mps` |
| `mode` | `flight_mode` |

### Example

```json
{
  "schema": "runtime-envelope.v1",
  "kind": "telemetry",
  "event_id": "3193d64f-2e56-4d55-bc1d-b33c72cbcae7",
  "mission_runtime_id": "flight_1743451200_8a4f8c2e",
  "db_flight_id": 128,
  "sequence": 42,
  "emitted_at": "2026-03-31T18:20:01.220Z",
  "source": "orchestrator.telemetry",
  "mission": {
    "mission_name": "Field Survey A",
    "mission_type": "photogrammetry",
    "mission_task_type": null,
    "preflight_run_id": "pf_72d99c82"
  },
  "payload": {
    "position": {
      "lat": 50.8476,
      "lon": 4.3572,
      "alt_m": 78.4,
      "relative_alt_m": 31.2
    },
    "attitude": {
      "roll_rad": 0.01,
      "pitch_rad": -0.03,
      "yaw_rad": 1.82,
      "roll_rate_rad_s": 0.0,
      "pitch_rate_rad_s": 0.0,
      "yaw_rate_rad_s": 0.0
    },
    "battery": {
      "voltage_v": 22.4,
      "current_a": 8.5,
      "remaining_pct": 74,
      "temperature_c": 31.0
    },
    "gps": {
      "satellites_visible": 18,
      "hdop": 0.9
    },
    "link": {
      "rc_quality_pct": 92,
      "telemetry_quality_pct": 88,
      "lte_quality_pct": null
    },
    "wind": {
      "speed_mps": 4.3,
      "direction_deg": 212.0
    },
    "motion": {
      "groundspeed_mps": 6.1,
      "airspeed_mps": 6.4,
      "heading_deg": 181.0,
      "throttle_pct": 52.0,
      "climb_mps": 0.0
    },
    "system": {
      "status": "ACTIVE"
    },
    "failsafe": {
      "state": "Normal"
    },
    "camera": {
      "gimbal_pitch_deg": null
    },
    "flight_mode": "AUTO",
    "armed": true,
    "coalesced_message_count": 4
  }
}
```

## Flight Event Envelope

### Canonical model

```python
class FlightEventSeverityV1(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

class FlightEventPayloadV1(BaseModel):
    event_name: str
    category: str | None = None
    severity: FlightEventSeverityV1 | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
```

### Decision notes

- `flight_event` is the generic operational event envelope.
- It is the canonical wrapper for what is currently stored in `flight_events` as
  `type + data`.
- Mission-specific event vocabularies remain free-form in `event_name`.
- `mission_lifecycle` is not represented as generic `flight_event` in the new
  bus, even if the system also persists a `mission_state_changed` audit row.

### Example

```json
{
  "schema": "runtime-envelope.v1",
  "kind": "flight_event",
  "event_id": "3489c676-37c0-4e9d-9191-4061c4cbe151",
  "mission_runtime_id": "flight_1743451200_8a4f8c2e",
  "db_flight_id": 128,
  "sequence": 43,
  "emitted_at": "2026-03-31T18:20:03.114Z",
  "source": "mission.photogrammetry",
  "mission": {
    "mission_name": "Field Survey A",
    "mission_type": "photogrammetry",
    "mission_task_type": null,
    "preflight_run_id": "pf_72d99c82"
  },
  "payload": {
    "event_name": "takeoff",
    "category": "navigation",
    "severity": "info",
    "attributes": {}
  }
}
```

## Video Health Envelope

### Canonical model

```python
class VideoHealthPayloadV1(BaseModel):
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
```

### Decision notes

- This payload unifies the current `DroneVideoStream.get_connection_status()`
  shape and the shared video runtime status shape.
- `recording_active` replaces the generic `recording` flag name.
- `source` is serialized as a string for consistency even when the underlying
  source is a numeric device index.

### Example

```json
{
  "schema": "runtime-envelope.v1",
  "kind": "video_health",
  "event_id": "a79bd90d-3fa0-4d62-b726-a9ab1a2899af",
  "mission_runtime_id": "flight_1743451200_8a4f8c2e",
  "db_flight_id": 128,
  "sequence": 44,
  "emitted_at": "2026-03-31T18:20:05.000Z",
  "source": "orchestrator.video",
  "mission": {
    "mission_name": "Field Survey A",
    "mission_type": "photogrammetry",
    "mission_task_type": null,
    "preflight_run_id": "pf_72d99c82"
  },
  "payload": {
    "stream_started": true,
    "healthy": true,
    "frame_count": 3298,
    "fps": 30.0,
    "resolution": "1280x720",
    "source": "udp://0.0.0.0:5600",
    "recording_active": true,
    "recording_file": "drone_video_20260331_182000.mp4",
    "recording_path": "/var/data/video/drone_video_20260331_182000.mp4",
    "error": null
  }
}
```

## Alert Event Envelope

### Canonical model

```python
AlertEventActionV1 = Literal["created", "updated", "acknowledged", "resolved"]
AlertSeverityV1 = Literal["info", "medium", "high", "critical"]
AlertStatusV1 = Literal["open", "acknowledged", "resolved"]

class AlertSnapshotV1(BaseModel):
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

class AlertEventPayloadV1(BaseModel):
    action: AlertEventActionV1
    alert: AlertSnapshotV1
```

### Decision notes

- `metadata` is the canonical field name; it replaces transport-specific
  `meta_data`.
- The alert snapshot mirrors the durable alert record shape closely so the bus,
  websocket layer, and alert API can share one model.

### Example

```json
{
  "schema": "runtime-envelope.v1",
  "kind": "alert_event",
  "event_id": "edc1ab22-02df-4f74-b10d-a48304d2db9f",
  "mission_runtime_id": "flight_1743451200_8a4f8c2e",
  "db_flight_id": 128,
  "sequence": 45,
  "emitted_at": "2026-03-31T18:20:06.104Z",
  "source": "alerts.engine",
  "mission": {
    "mission_name": "Field Survey A",
    "mission_type": "photogrammetry",
    "mission_task_type": null,
    "preflight_run_id": "pf_72d99c82"
  },
  "payload": {
    "action": "created",
    "alert": {
      "alert_id": 88,
      "rule_type": "low_battery",
      "dedupe_key": "drone.low_battery",
      "source": "drone",
      "severity": "high",
      "status": "open",
      "title": "Low Battery",
      "message": "Battery dropped to 24% (threshold 25%).",
      "metadata": {
        "battery_remaining": 24,
        "threshold_percent": 25
      },
      "first_triggered_at": "2026-03-31T18:20:06.100Z",
      "last_triggered_at": "2026-03-31T18:20:06.100Z",
      "last_notified_at": "2026-03-31T18:20:06.100Z",
      "resolved_at": null,
      "acknowledged_at": null,
      "acknowledged_by_user_id": null,
      "occurrences": 1
    }
  }
}
```

## Mission Lifecycle Envelope

### Canonical model

```python
MissionLifecycleStateV1 = Literal[
    "queued",
    "running",
    "paused",
    "aborted",
    "completed",
    "failed",
]

class MissionLifecyclePayloadV1(BaseModel):
    state: MissionLifecycleStateV1
    previous_state: MissionLifecycleStateV1 | None = None
    trigger: str
    reason: str | None = None
    error: str | None = None
    command_id: str | None = None
    requested_by_user_id: int | None = None
```

### Decision notes

- This payload is the canonical representation of mission runtime state changes.
- It is distinct from generic `flight_event`.
- Current v1 states match the current route/runtime implementation exactly:
  `queued`, `running`, `paused`, `aborted`, `completed`, `failed`.
- If preflight or startup substates are later promoted to first-class lifecycle
  states, that should be a schema revision rather than an ad hoc extension.

### Example

```json
{
  "schema": "runtime-envelope.v1",
  "kind": "mission_lifecycle",
  "event_id": "3ce78171-e9cf-4877-b84a-cc1ad1f11e3c",
  "mission_runtime_id": "flight_1743451200_8a4f8c2e",
  "db_flight_id": 128,
  "sequence": 46,
  "emitted_at": "2026-03-31T18:20:07.000Z",
  "source": "orchestrator.lifecycle",
  "mission": {
    "mission_name": "Field Survey A",
    "mission_type": "photogrammetry",
    "mission_task_type": null,
    "preflight_run_id": "pf_72d99c82"
  },
  "payload": {
    "state": "paused",
    "previous_state": "running",
    "trigger": "command:pause",
    "reason": null,
    "error": null,
    "command_id": "cmd_1743451207_08d82a56ec",
    "requested_by_user_id": 7
  }
}
```

## Migration Mapping from Current Producers

### Current websocket telemetry

Current:

```json
{ "type": "telemetry", "data": { ... } }
```

Canonical:

- `type` becomes `kind`
- `data` becomes typed `payload`
- `mode` becomes `payload.flight_mode`
- `status` becomes `payload.motion`

### Current alert websocket events

Current:

```json
{ "type": "alert_event", "action": "created", "alert": { ... } }
```

Canonical:

- `kind` is `alert_event`
- `payload.action` keeps the same semantic value
- `payload.alert.meta_data` becomes `payload.alert.metadata`

### Current video MQTT payload

Current:

```json
{
  "timestamp": 1710000000.0,
  "healthy": true,
  "frame_count": 123,
  "fps": 30,
  "resolution": "1280x720",
  "recording": false,
  "recording_file": null
}
```

Canonical:

- `recording` becomes `recording_active`
- envelope timestamp becomes `emitted_at`
- optional `recording_path`, `source`, and `error` are standardized

### Current mission runtime and mission_state_changed records

Current sources:

- `MissionRuntimeOut`
- `mission_state_changed` persisted flight events
- `mission_command` persisted flight events

Canonical:

- state transition events emit `kind = "mission_lifecycle"`
- generic audit items still emit `kind = "flight_event"`

## Implementation Guidance for the Next Step

The next typed-model implementation should:

1. implement the five payload models and the shared base envelope exactly as
   specified here
2. add adapters from current websocket, alert, video, and mission lifecycle
   producers into these models
3. keep legacy outward payload shapes only behind transport adapters where
   compatibility is still required
