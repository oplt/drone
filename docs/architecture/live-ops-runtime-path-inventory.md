# Live-Ops Runtime Path Inventory

## Status
Current-state inventory

## Date
2026-03-31

## Purpose

This document inventories the current MAVLink, telemetry, event, websocket,
MQTT, alerts, ML, and DB write paths in the repository before the live-ops
runtime refactor. It is the supporting inventory for
`docs/adr/ADR-001-canonical-live-ops-runtime-architecture.md`.

For the current end-to-end hot-path drawing and inconsistency markers, see
`docs/architecture/live-ops-hot-path-current-state.md`.

The goal is to make three things explicit:

1. Which modules currently own live readers and transforms.
2. Which modules consume global runtime state.
3. Where duplicate readers, duplicate transforms, and dead write paths already
   exist.

## Composition Root

### Runtime bootstrap

- `backend/main.py`
  - builds `MavlinkDrone`
  - builds `MqttClient`
  - builds `MqttPublisher`
  - builds `TelemetryRepository`
  - injects all of them into `Orchestrator`
- `backend/api/api_main.py`
  - initializes `telemetry_manager`
  - sets the websocket manager event loop
  - starts `alert_engine`
- `backend/drone/orchestrator.py`
  - starts telemetry websocket streaming during `run_mission()`
  - starts MQTT publishing
  - starts MQTT subscription for raw-event ingestion
  - starts raw MAVLink event DB ingestion worker
  - starts video health and emergency monitors
- `backend/api/routes/routes_flights.py`
  - can also start and stop telemetry directly through `/tasks/telemetry/start`
    and `/tasks/telemetry/stop`

### Architectural meaning

- Flight control is composed in the orchestrator.
- Telemetry websocket runtime is composed separately in API startup.
- Alert evaluation is composed separately in API startup.
- ML runtime is started separately through `/api/ml/start`.
- This means live operations are already split across multiple runtime owners
  before any mission begins.

## Current Live Readers and Upstream Sources

| Path | Source | Current owner | Transform | Outputs | Duplicate / risk |
| --- | --- | --- | --- | --- | --- |
| Flight-control MAVLink connection | Vehicle connection string from `settings.drone_conn` | `backend/drone/mavlink_drone.py` via DroneKit `connect()` | DroneKit vehicle state plus helper methods like `get_telemetry()` | Mission execution, mode changes, takeoff, waypoint following, camera/video commands | Separate control-plane connection from telemetry readers |
| Websocket telemetry reader | MAVLink from `settings.drone_conn_mavproxy` | `backend/messaging/websocket.py` `start_telemetry_stream()` | `_process_mavlink_message()` converts MAVLink packets into UI-oriented `last_telemetry` sections | `/ws/telemetry`, `telemetry_manager.last_telemetry`, analytics health, alerts, ML context, mission status APIs | Duplicate MAVLink reader |
| MQTT publisher reader | MAVLink from `settings.drone_conn_mavproxy` | `backend/messaging/mqtt.py` `MqttPublisher` | `msg.to_dict()` plus `timestamp` JSON serialization | MQTT broker topic `settings.telemetry_topic` | Duplicate MAVLink reader |
| MQTT subscriber | MQTT topic `settings.telemetry_topic` | `backend/messaging/mqtt.py` `MqttClient` | `_process_raw_event()` wraps MQTT payload as raw event row input | `orchestrator._raw_event_queue` -> `MavlinkEvent` DB writes | Downstream of duplicate MAVLink reader |
| ML video reader | Video stream source from ML config | `backend/ml/patrol/pipeline.py` via `StreamReader` | Motion prefilter, detector, tracker, geo projection, anomaly scoring | websocket ML events, patrol persistence, outbound event sink | Separate live path, not coordinated with telemetry lifecycle |

## Current Telemetry and Event Transforms

| Transform | Module | Input | Output | Notes |
| --- | --- | --- | --- | --- |
| MAVLink -> browser telemetry model | `backend/messaging/websocket.py` `_process_mavlink_message()` | MAVLink message dicts from `GLOBAL_POSITION_INT`, `VFR_HUD`, `BATTERY_STATUS`, `ATTITUDE`, `HEARTBEAT`, `GPS_RAW_INT`, `SYS_STATUS`, `RADIO_STATUS`, `RC_CHANNELS`, `WIND`, `STATUSTEXT` | `telemetry_manager.last_telemetry` structure with sections like `position`, `battery`, `gps`, `link`, `wind`, `failsafe`, `status`, `mode`, `armed` | This is the canonical live telemetry shape for most of the app today, but it lives inside websocket infrastructure |
| MAVLink -> MQTT payload | `backend/messaging/mqtt.py` `MqttPublisher._publish_loop()` | Raw MAVLink messages from `recv_match()` | `msg.to_dict()` plus timestamp JSON | This is a second transform of the same upstream telemetry, but into a different schema |
| MQTT payload -> raw DB event envelope | `backend/messaging/mqtt.py` `MqttClient._process_raw_event()` | JSON payload from broker | Dict with `flight_id`, `msg_type`, `time_boot_ms`, `time_unix_usec`, `timestamp`, `payload` | This transform is for persistence only and is downstream of the second MAVLink reader |
| Telemetry cache -> alert signals | `backend/services/alerts/engine.py` | `telemetry_manager.last_telemetry` | `AlertSignal` list for low battery, weak link, high wind, geofence breach | Alert logic depends on websocket cache, not on a canonical runtime bus |
| Telemetry cache -> ML geo context | `backend/ml/patrol/pipeline.py` `_get_latest_telemetry()` | `telemetry_manager.last_telemetry` | Reduced ML telemetry dict with `lat`, `lon`, `altitude_m`, `heading`, `groundspeed`, `gimbal_pitch_deg`, `timestamp` | ML derives its own projection of websocket telemetry |
| Mission/runtime state -> API status payload | `backend/api/routes/routes_flights.py` `/tasks/flight/status` | `_mission_runtimes`, `_active_mission_runtime_id`, `telemetry_manager.last_telemetry`, orchestrator state | Polled mission status payload consumed by frontend | Runtime status is assembled in the route layer |
| Alert DB row -> websocket event | `backend/services/alerts/engine.py` and `backend/api/routes/routes_alerts.py` | `OperationalAlert` ORM objects | `alert_event` websocket payloads | Created, updated, resolved, acknowledged paths are split across engine and routes |
| ML anomaly -> websocket event | `backend/ml/patrol/events.py` | `PipelineEvent` and system messages | `ml_anomaly_event` and `ml_status` websocket payloads | Separate event family on same websocket channel |

## Current Websocket Producers

| Producer | Event types | Transport owner | Notes |
| --- | --- | --- | --- |
| `backend/messaging/websocket.py` telemetry worker | `telemetry` | `telemetry_manager.broadcast_bytes()` | Main live telemetry feed |
| `backend/services/alerts/engine.py` | `alert_event` with `created`, `updated`, `resolved` actions | `telemetry_manager.broadcast()` | In-app alerts depend on websocket manager |
| `backend/api/routes/routes_alerts.py` | `alert_event` with `acknowledged`, `resolved` actions | `telemetry_manager.broadcast()` | Route layer is also a websocket event producer |
| `backend/ml/patrol/events.py` | `ml_anomaly_event`, `ml_status` | `telemetry_manager.broadcast()` | ML publishes over the same websocket manager |
| `backend/api/routes/routes_ml.py` | `ml_status` test message | `telemetry_manager.broadcast()` | Debug or simulated producer |

## Current Websocket Consumers

| Consumer | Entry point | What it uses |
| --- | --- | --- |
| Browser websocket route | `backend/api/routes/routes_websocket.py` `/ws/telemetry` | Registers clients with `telemetry_manager` |
| Shared frontend telemetry hook | `frontend/src/hooks/useTelemetryWebsocket.ts` | Connects to `/ws/telemetry`, parses `telemetry`, `alert_event`, and `ml_*` messages |
| Mission runtime hook | `frontend/src/hooks/useMissionWebsocketRuntime.tsx` | Combines polled mission status with websocket telemetry |
| Alert center | `frontend/src/contexts/AlertCenterContext.tsx` | Consumes `alert_event` messages and refreshes alert counts |
| Dashboard pages | `FleetPage.tsx`, `InsightsPage.tsx`, `MainGrid.tsx`, mission pages | Consume telemetry hook directly or through mission runtime hook |

## Current MQTT Paths

### Outbound MQTT

1. `backend/messaging/mqtt.py` `MqttPublisher` opens its own MAVLink connection.
2. `MqttPublisher._publish_loop()` reads selected MAVLink message types.
3. Each MAVLink message is converted to JSON with `msg.to_dict()`.
4. The payload is published to `settings.telemetry_topic`.

### Inbound MQTT

1. `backend/drone/orchestrator.py` `mqtt_subscriber_task()` attaches
   `_raw_event_queue` to `MqttClient`.
2. `MqttClient.subscribe_to_topics()` subscribes to `settings.telemetry_topic`.
3. `MqttClient._on_message()` decodes JSON and calls `_process_raw_event()`.
4. `_process_raw_event()` pushes raw event dicts into `_raw_event_queue`.
5. `Orchestrator._raw_event_ingest_worker()` batches the queue into
   `TelemetryRepository.add_mavlink_events_many()`.

### Inventory conclusion

- MQTT is currently both a live integration output and the ingestion path for
  raw event persistence.
- Because outbound MQTT itself is fed by a second MAVLink reader, raw event
  persistence is not fed from the same source that powers browser telemetry.

## Current DB Write Paths

| Write path | Module | Tables / records | Trigger |
| --- | --- | --- | --- |
| Flight record creation | `backend/drone/orchestrator.py` -> `TelemetryRepository.create_flight()` | `flights` | Mission start |
| Flight event writes | `backend/drone/orchestrator.py` -> `TelemetryRepository.add_event()` | `flight_events` | Mission lifecycle, preflight report, connected, mission failed, mission aborted, video recording events |
| Flight finish / state changes | `backend/drone/orchestrator.py` -> `TelemetryRepository.finish_flight_if_in_progress()` and `set_flight_status_if_active()` | `flights` | Mission completion, interruption, failure |
| Raw MAVLink event batching | `backend/drone/orchestrator.py` `_raw_event_ingest_worker()` -> `TelemetryRepository.add_mavlink_events_many()` | `mavlink_event` | MQTT subscriber path |
| Alert rule persistence | `backend/services/alerts/engine.py` -> `AlertRepository.create_alert()`, `touch_alert()`, `resolve_alert()` | `operational_alerts`, `alert_deliveries` | Periodic alert evaluation |
| Alert operator actions | `backend/api/routes/routes_alerts.py` -> `AlertRepository.acknowledge_alert()`, `resolve_by_id()` | `operational_alerts` | Operator acknowledgement and resolution |
| Patrol/ML persistence | `backend/services/patrol/patrol_persistence.py` -> `PatrolDetectionRepository.persist_detection_pipeline_result()` | `patrol_detection`, `patrol_incident`, `patrol_incident_detection`, optional `operational_alerts`, plus summary `flight_events` | ML anomaly accepted for persistence |

## Live DB Write Paths That Exist But Are Not Currently Wired

| Path | Current state | Why it matters |
| --- | --- | --- |
| `backend/drone/orchestrator.py` `_ingest_queue` | Allocated but not consumed by a live worker | Suggests intended telemetry pipeline that never became the active path |
| `backend/messaging/mqtt.py` `attach_ingest_queue()` | Defined but not used | Another sign of incomplete telemetry ingest design |
| `backend/db/repository/telemetry_repo.py` `add_telemetry()` | Implemented but not used by the live mission path | Telemetry row persistence is not on the main hot path today |
| `backend/db/repository/telemetry_repo.py` `add_telemetry_many()` | Implemented but not used by the live mission path | Bulk telemetry persistence exists in code but not in runtime wiring |

## Current Alert and ML Dependency Paths

### Alert dependency path

1. `telemetry_manager.last_telemetry` is updated only by the websocket telemetry
   worker.
2. `AlertEngine.evaluate_once()` reads that global cache.
3. Alert rule evaluation writes alert rows through `AlertRepository`.
4. In-app notifications are emitted back through `telemetry_manager.broadcast()`.
5. External notifications are emitted through email or SMS adapters.

### ML dependency path

1. `ml_runtime` starts `DroneAnomalyPipeline` on demand.
2. The pipeline reads video frames via `StreamReader`.
3. The pipeline reads current drone position and heading from
   `telemetry_manager.last_telemetry`.
4. `EventDispatcher` emits websocket events through `telemetry_manager`.
5. `PatrolPersistenceService.persist_anomaly()` writes patrol detections,
   incidents, optional alerts, and summary flight events to the database.

### Inventory conclusion

- Alerts and ML both depend on `telemetry_manager.last_telemetry` as an implicit
  shared runtime store.
- Neither path currently subscribes to a canonical orchestrator-owned runtime
  stream.

## Current Frontend Runtime Dependency Path

1. `frontend/src/hooks/useMissionStatusPolling.tsx` polls
   `/tasks/flight/status` every 5 seconds.
2. `frontend/src/hooks/useMissionWebsocketRuntime.tsx` uses that polled status
   to decide whether a websocket connection should be enabled.
3. `frontend/src/hooks/useTelemetryWebsocket.ts` connects to `/ws/telemetry`.
4. Frontend pages and contexts consume telemetry, alerts, and ML events from
   the same websocket stream.

### Inventory conclusion

- Mission lifecycle state is not websocket-native in the frontend.
- Websocket telemetry and HTTP-polled mission runtime are combined client-side.
- The browser depends on both `routes_flights.py` runtime assembly and
  `telemetry_manager` telemetry state.

## Duplicate Readers

### Duplicate live readers against vehicle telemetry

- `backend/drone/mavlink_drone.py`
  - owns the DroneKit control-plane connection to the vehicle
- `backend/messaging/websocket.py`
  - opens a direct MAVLink telemetry connection for browser telemetry
- `backend/messaging/mqtt.py` `MqttPublisher`
  - opens another direct MAVLink connection for MQTT republishing

### Why this matters

- The system can observe the same flight through multiple readers with
  different timing and reconnect behavior.
- Browser telemetry and MQTT/raw-event persistence are not guaranteed to see
  the same message sequence.
- Refactoring must treat the websocket telemetry reader and MQTT publisher
  reader as first-class duplicates, not merely separate integrations.

## Duplicate Transforms

### Duplicate or overlapping transforms

- MAVLink -> UI telemetry model in `backend/messaging/websocket.py`
- MAVLink -> MQTT JSON in `backend/messaging/mqtt.py`
- MQTT JSON -> raw DB event envelope in `backend/messaging/mqtt.py`
- Websocket telemetry cache -> alert signals in `backend/services/alerts/engine.py`
- Websocket telemetry cache -> ML telemetry projection in
  `backend/ml/patrol/pipeline.py`
- Mission runtime assembly in `backend/api/routes/routes_flights.py`
  plus overlapping runtime projection in `backend/services/patrol/mission_runtime_store.py`

### Why this matters

- Transform logic is scattered across transport modules and feature modules.
- The same conceptual runtime state is projected into several incompatible
  shapes before persistence or UI delivery.
- Refactoring should isolate one canonical envelope contract before replacing
  transport-specific transforms.

## Global Mutable Runtime State

| Global state | Current owner | Current dependents |
| --- | --- | --- |
| `telemetry_manager.last_telemetry` | `backend/messaging/websocket.py` | alerts engine, ML pipeline, analytics route, flight status route, drone position route, frontend websocket clients |
| `telemetry_manager._running` and `mav_conn` | `backend/messaging/websocket.py` | API health, analytics route, flight status route, telemetry control routes |
| `_preflight_runs` | `backend/api/routes/routes_flights.py` | flight API route handlers |
| `_mission_runtimes` and `_active_mission_runtime_id` | `backend/api/routes/routes_flights.py` | flight status and mission lifecycle APIs |
| `mission_runtime_store` | `backend/services/patrol/mission_runtime_store.py` | patrol persistence and ML runtime context |

## Refactor-Critical Findings

1. Browser telemetry and MQTT republishing are fed by separate MAVLink readers.
2. Raw MAVLink event persistence is downstream of the MQTT path, not the
   browser telemetry path or the flight-control path.
3. Alerts and ML consume websocket cache state, not a dedicated runtime bus.
4. Mission runtime state is duplicated between route globals and the patrol
   runtime store.
5. Bulk telemetry persistence code exists but is not wired into the active
   runtime path.
6. Frontend live runtime depends on both polling and websocket telemetry.

## Recommended Use of This Inventory

- Use this inventory together with ADR-001 before touching runtime ownership.
- Preserve the list of duplicate readers until each one is removed or
  re-scoped.
- Treat unwired telemetry write paths as implementation debt, not as evidence
  that telemetry persistence is already solved.
