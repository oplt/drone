# Property Patrol Mission Integration Audit

## Existing Backend Reuse

- Mission runtime/API: `backend/modules/missions/api/routes.py`, `backend/modules/missions/runtime_models.py`, `backend/modules/missions/domain/state_machine.py`.
- Patrol planning/video AI: `backend/modules/patrol/planning.py`, `backend/modules/patrol/vision/*`, `backend/modules/patrol/live_detection_api.py`, `backend/modules/patrol/vision_api.py`.
- Existing patrol incident/detection persistence: `backend/modules/patrol/models.py`.
- MAVLink/runtime boundary: `backend/infrastructure/vehicle/mavlink_client.py`, `backend/modules/vehicle_runtime/*`.
- Telemetry/live updates: `backend/modules/telemetry/*`, `backend/infrastructure/messaging/websocket_publisher.py`.
- Mapping/geofence patterns: `backend/modules/fields/*`, `backend/modules/geofences/*`, `backend/modules/mapping/*`.
- Preflight patterns: `backend/modules/preflight/checks/*`.
- Logging/metrics: `backend/core/logging/*`, `backend/core/observability/metrics.py`.
- ORM/Alembic pattern: `backend/core/database/model_registry.py`, `backend/infrastructure/persistence/alembic/versions/*`.

## Existing Frontend Reuse

- Current private patrol workflow: `frontend/src/modules/private-patrol/*`.
- Mission runtime telemetry/video/commands: `frontend/src/modules/mission-runtime/*`.
- Map drawing/display: `frontend/src/modules/maps/*`, `frontend/src/modules/mission-workflow/*`.
- Field/map polygon storage: `frontend/src/modules/fields/*`, `frontend/src/modules/field-survey/*`.
- API client convention: `frontend/src/shared/api/httpClient.ts`.
- Routing/layout: `frontend/src/app/routes/AppRouter.tsx`, `frontend/src/shared/layout/*`.

## Implemented Pieces

- New `backend/modules/property_patrol` domain with typed models, schemas, services, and API.
- JSON GeoJSON persistence for site boundaries/zones. PostGIS exists elsewhere, but this feature stores GeoJSON to avoid new spatial migrations and keep API payloads stable.
- Policy engine validates waypoints inside `flight_safe_area`, outside `no_fly_zones`, altitude/speed/duration/battery thresholds, and sensor locations.
- Route planner reuses existing private patrol perimeter/grid helpers from `backend/modules/patrol/planning.py`.
- Sensor event endpoint deduplicates `site_id + external_event_id`, validates freshness/confidence/location, and creates incidents without direct drone movement.
- State machine blocks invalid transitions like `DRAFT -> TAKEOFF` and terminal-state restarts.
- Preflight validator extension point checks route/telemetry inputs and warns when live telemetry is unavailable.
- Frontend route `/dashboard/property-patrol` plus typed API client and management page. Existing `/dashboard/privatepatrol` remains as compatibility alias with user-facing text renamed.

## Integration Points

- Replace the dispatch stub in `PatrolDispatchService.dispatch_after_preflight` with existing mission launch service once a real aircraft/SITL context is selected.
- Publish Property Patrol Mission state updates through existing telemetry websocket publisher.
- Connect `PropertyPatrolIncident.llm_summary` to `backend/infrastructure/ai/llm_client.py` using metadata/keyframes only.
- Feed YOLO detections from `backend/modules/patrol/vision/pipeline.py` into `/api/property-patrol/incidents` or a service-level incident creator.
- Reuse existing mission command audit tables if operator actions need cross-mission reporting.

## Risks And Compatibility Notes

- No heavy dependency added. Shapely was already used by existing patrol/field code.
- JSON GeoJSON avoids adding PostGIS-specific Property Patrol columns, but spatial indexes are not available for these new tables.
- Dispatch currently records validated/preflighted runs and state transitions; real MAVLink/ROS mission upload is intentionally left behind the existing runtime integration boundary.
- Sensor events require explicit `site_id`; coordinates never choose a site or command a drone implicitly.
- Existing private patrol route and mission type names remain in code for backward compatibility, but user-facing labels now say `Property Patrol Mission`.

