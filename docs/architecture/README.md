# Architecture Inventories

This directory contains current-state architecture inventories that support
refactors and ADR work.

## Index

- `live-ops-hot-path-current-state.md`: current end-to-end hot-path map from
  vehicle input through websocket, MQTT, alerts, ML, DB writes, and UI
- `live-ops-runtime-path-inventory.md`: current MAVLink, telemetry, websocket,
  MQTT, alerts, ML, and DB write paths across the live operations stack
- `runtime-envelope-schemas-v1.md`: canonical runtime envelope schemas for the
  orchestrator-owned live-ops bus

## Related ADRs

- `../adr/ADR-001-canonical-live-ops-runtime-architecture.md`
