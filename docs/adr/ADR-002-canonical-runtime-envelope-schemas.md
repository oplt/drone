# ADR-002: Canonical Runtime Envelope Schemas

## Status
Accepted

## Date
2026-03-31

## Context

ADR-001 established that the platform needs one canonical live-ops runtime
boundary owned by the orchestrator. The next missing decision is the contract
that boundary emits.

Today, the runtime produces several incompatible payload shapes:

- websocket telemetry uses `{"type": "telemetry", "data": ...}`
- alert events use `{"type": "alert_event", "action": ..., "alert": ...}`
- ML emits `ml_anomaly_event` and `ml_status`
- video health is published to MQTT as an ad hoc status payload
- mission lifecycle is split between route-layer runtime objects and persisted
  `flight_events`
- generic flight events are stored as `type + data` rows in `flight_events`

Without a canonical schema, the next implementation step would only replace ad
hoc dicts with typed ad hoc dicts.

## Decision

The platform adopts a single outer runtime envelope schema,
`runtime-envelope.v1`, and five canonical payload families:

1. `telemetry`
2. `flight_event`
3. `video_health`
4. `alert_event`
5. `mission_lifecycle`

The detailed schema definitions live in:

- `docs/architecture/runtime-envelope-schemas-v1.md`

Key decisions:

- `mission_runtime_id` is the canonical runtime identifier and maps to the
  current `client_flight_id`.
- `db_flight_id` is the durable `flights.id` when persistence has been created.
- `mission_lifecycle` is a first-class runtime event kind and is not collapsed
  into generic `flight_event`.
- `flight_event` remains the generic operational audit/event payload for
  mission-specific and subsystem-specific events.
- `telemetry` is a normalized snapshot payload, not a raw MAVLink packet.
- `alert_event` uses a canonical `alert` snapshot shape with `metadata`, not
  transport-specific `meta_data`.
- `video_health` unifies the currently split `DroneVideoStream` and shared video
  runtime status shapes.

## Consequences

### Positive

- The next step can implement one set of typed backend models instead of
  perpetuating transport-specific payloads.
- Alerts, websocket delivery, MQTT output, replay, and UI adapters can all map
  from one contract.
- Mission lifecycle state transitions become explicitly distinct from generic
  flight events.

### Negative

- Several existing field names will need adapters or translation layers during
  rollout.
- Legacy websocket payloads and MQTT payloads may need compatibility shims until
  downstream consumers are migrated.

## Supporting References

- `docs/architecture/runtime-envelope-schemas-v1.md`
- `docs/architecture/live-ops-runtime-path-inventory.md`
- `docs/architecture/live-ops-hot-path-current-state.md`
- `docs/adr/ADR-001-canonical-live-ops-runtime-architecture.md`
