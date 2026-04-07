# ADR-001: Canonical Live-Ops Runtime Architecture

## Status
Accepted

## Date
2026-03-31

## Context

The current live-operations path is functionally rich but architecturally split
across multiple owners:

- `backend/drone/orchestrator.py` already coordinates core flight concerns such
  as drone connection, mission lifecycle, preflight checks, video health, MQTT
  integration, and flight persistence.
- `backend/messaging/websocket.py` owns its own MAVLink connection and telemetry
  broadcast thread for browser clients.
- `backend/messaging/mqtt.py` contains both the MQTT subscriber path and
  `MqttPublisher`, which also opens its own MAVLink connection and republishes
  selected messages.
- `backend/api/routes/routes_flights.py` stores active mission runtime and
  preflight state in module-level dictionaries such as `_preflight_runs`,
  `_mission_runtimes`, and `_active_mission_runtime_id`.
- `backend/services/patrol/mission_runtime_store.py` introduces a second mission
  runtime store that overlaps with the route-layer runtime tracking.

This creates four concrete problems:

1. Telemetry ingest has multiple owners.
   Result: duplicated MAVLink reads, inconsistent event ordering, and more than
   one hot-path code path that can fail independently.
2. Mission runtime ownership is ambiguous.
   Result: API handlers and patrol services each act like a source of truth.
3. Persistence boundaries are weak.
   Result: live mission state is partly durable and partly process-local, which
   breaks restart recovery and makes auditability weaker.
4. Downstream consumers are coupled to transport details.
   Result: websocket, MQTT, alerts, ML, and persistence code each make
   assumptions about upstream message shape and timing.

The product goal is not to introduce microservices. This codebase is still best
served by a modular monolith, but it needs a single canonical runtime boundary
inside that monolith.

## Decision

The platform will adopt a single canonical live-ops architecture inside the
existing backend process.

### 1. Telemetry ingest ownership

`backend/drone/orchestrator.py` is the sole owner of live runtime ingest for a
connected vehicle.

- The orchestrator owns vehicle-adjacent runtime concerns:
  - telemetry normalization
  - mission lifecycle event emission
  - video health event emission
  - command acknowledgements
  - handoff into persistence and external transports
- No other module may open an independent MAVLink connection for browser
  telemetry broadcasting or MQTT republishing.
- `backend/messaging/websocket.py` becomes a runtime subscriber and broadcaster,
  not a MAVLink reader.
- `backend/messaging/mqtt.py` keeps broker client responsibilities, but message
  production is driven by orchestrator-emitted envelopes rather than a second
  direct MAVLink reader.

### 2. Canonical mission runtime ownership

Mission runtime state is owned by a dedicated backend runtime service beneath
the API layer and above the repository layer.

- `backend/api/routes/routes_flights.py` must not remain the owner of active
  runtime state through module-level dictionaries.
- The API layer may start, update, or query mission runtime state, but it does
  so through a mission-runtime service.
- `backend/services/patrol/mission_runtime_store.py` is not a second source of
  truth. Patrol/ML code may cache or project runtime state, but the canonical
  mission runtime record is shared and durable.
- Preflight runs follow the same rule: route handlers do not own their primary
  state.

### 3. Persistence boundaries

The system separates hot-path runtime transport from durable system-of-record
storage.

- Durable system-of-record data:
  - mission runtime state transitions
  - preflight runs and outcomes
  - operator commands
  - mission events
  - downsampled telemetry used for replay and analytics
  - raw MAVLink or diagnostics payloads retained under explicit retention rules
- Process-local or ephemeral data:
  - short-lived fan-out queues
  - websocket client buffers
  - in-flight debouncing and batching buffers
  - optional caches that can be rebuilt from durable state

Persistence ownership sits behind repository or service boundaries such as
`backend/db/repository/telemetry_repo.py` and future mission-runtime
repositories. Process-local structures may exist for performance, but they are
never treated as the canonical source of truth.

### 4. Downstream consumers

All downstream consumers subscribe to normalized runtime envelopes instead of
reading vehicle protocols directly.

Required downstream consumer classes:

- persistence consumer
  - writes mission events, telemetry batches, and raw diagnostics
- websocket consumer
  - publishes operator-facing live runtime updates
- MQTT consumer
  - republishes selected normalized events to external systems
- alerts consumer
  - evaluates safety and operational thresholds
- ML/patrol consumer
  - consumes normalized telemetry and event context
- analytics/replay consumer
  - builds replay-friendly read models and summaries

### 5. Canonical runtime envelope contract

The orchestrator emits typed runtime envelopes with at least:

- `kind`
  - one of `telemetry`, `mission_event`, `alert_source_event`,
    `video_health`, `command_event`, `raw_diagnostic`
- `flight_id`
- `mission_runtime_id`
- `sequence`
- `emitted_at`
- `source`
- `payload`

Envelope rules:

- Sequence is monotonic per mission runtime.
- High-frequency telemetry may be sampled or coalesced downstream, but mission
  lifecycle events must not be dropped silently.
- Consumers are responsible for their own backpressure policy, but that policy
  is explicit and observable.

### 6. Architectural style

This decision standardizes on an in-process event-driven modular monolith, not
an external broker as the primary control-plane dependency.

- Internal async queues are the default fan-out mechanism.
- External brokers such as MQTT are integration outputs, not the internal
  source of truth.
- A future external event bus remains possible, but only after the runtime
  contract and ownership boundaries are stable inside the application.

## Options Considered

### Option A: Keep the current multi-owner runtime model

- Pros:
  - no short-term refactor cost
  - each module can evolve independently
- Cons:
  - duplicated vehicle readers remain
  - restart safety remains weak
  - runtime behavior stays harder to reason about and test
  - downstream consumers stay tightly coupled to transport details

Rejected because it preserves the current failure modes.

### Option B: Move immediately to an external broker-centric architecture

- Pros:
  - strong decoupling between producers and consumers
  - easier horizontal scaling later
- Cons:
  - adds infrastructure and operational complexity now
  - pushes core correctness into distributed-systems concerns too early
  - does not solve unclear domain ownership by itself

Rejected for now because the team and product stage are better served by a
clear modular-monolith boundary first.

### Option C: Orchestrator-owned runtime bus with durable mission runtime

- Pros:
  - one live ingest owner
  - explicit ownership of runtime and preflight state
  - simpler observability and failure handling
  - supports future replay, compliance, and fleet workflows cleanly
- Cons:
  - requires a hot-path refactor
  - requires schema and service-layer changes
  - requires careful rollout to avoid regressions

Accepted.

## Consequences

### Positive

- Runtime behavior becomes easier to reason about because the vehicle-facing
  ingest path has one owner.
- Mission runtime and preflight state become durable and restart-safe.
- Replay, analytics, and alerting gain a cleaner contract to build on.
- Websocket, MQTT, and ML integrations become easier to test because they
  subscribe to normalized envelopes instead of protocol-specific state.

### Negative

- `backend/drone/orchestrator.py` becomes a more important architectural
  boundary and must be kept disciplined.
- The first implementation phase will touch critical operational code.
- Some existing module responsibilities will shrink or move, which may require
  incremental refactoring rather than a single cutover.

## Implementation Boundaries

The decision implies the following target boundaries:

- `backend/drone/orchestrator.py`
  - owns runtime ingest, envelope creation, and consumer fan-out
- `backend/messaging/websocket.py`
  - owns websocket connection management and live client broadcast only
- `backend/messaging/mqtt.py`
  - owns MQTT broker integration only
- `backend/api/routes/routes_flights.py`
  - owns HTTP request/response handling only
- `backend/services/patrol/mission_runtime_store.py`
  - becomes a projection/cache or is merged into the canonical runtime service
- `backend/db/repository/telemetry_repo.py`
  - owns durable telemetry and event persistence contracts

## Rollout Plan

1. Define typed runtime envelopes and queue contracts.
2. Add a mission-runtime service and durable mission/preflight records.
3. Refactor websocket and MQTT paths to subscribe to orchestrator output.
4. Run the new envelope path in shadow mode alongside existing outputs.
5. Compare telemetry/event parity, queue lag, and failure behavior.
6. Remove duplicate vehicle readers and route-layer runtime ownership.

## Supporting References

- `docs/adr/ADR-002-canonical-runtime-envelope-schemas.md`
- `docs/architecture/runtime-envelope-schemas-v1.md`
- `docs/architecture/live-ops-hot-path-current-state.md`
- `docs/architecture/live-ops-runtime-path-inventory.md`

## Guardrails

- No new module may open a second live vehicle telemetry reader for operator
  runtime features.
- Route modules must not own canonical mission or preflight state.
- New consumers must subscribe to normalized envelopes, not MAVLink messages.
- Any exception to these rules requires a superseding ADR.
