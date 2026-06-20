# Mission launch architecture

All launch paths converge on the vehicle runtime. HTTP routers validate identity
and request shape; application services own planning, preflight, persistence, and
dispatch.

```mermaid
flowchart LR
  U[Operator / scheduler] --> O[Outdoor tasks API]
  U --> W[Warehouse API]
  U --> P[Property patrol API]

  O --> OS[mission_start service]
  W --> WS[warehouse mission_launch service]
  P --> PS[PatrolDispatchService]

  OS --> OP[Outdoor MAVLink preflight]
  WS --> RP[Warehouse ROS preflight snapshot]
  PS --> PP[Patrol policy + route preflight]

  PP --> OS
  OP --> R[Vehicle runtime orchestrator]
  RP --> R

  R --> D[(Mission runtime + flight records)]
  R --> V[Drone adapter: MAVLink / local ROS]
  R --> T[Telemetry + lifecycle events]
```

Ownership rules:

- Outdoor mission construction and persisted preflight tokens belong to
  `backend/modules/missions/service`.
- Warehouse UI readiness snapshots and background ROS probes belong to
  `backend/modules/warehouse/service/preflight_*`.
- Warehouse flight readiness is a domain gate, not a second mission launcher.
- Property patrol validates site policy first, then delegates real launch to
  `start_mission_for_user`; it must not mark a run dispatched without runtime acceptance.
- Orchestrator construction belongs to `vehicle_runtime/factory.py`; HTTP modules
  never import CLI entrypoints.
