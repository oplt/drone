# Property Patrol Mission

## Architecture

Property Patrol Mission adds a bounded workflow:

1. Frontend/operator creates a site with GeoJSON property boundary, safe area, no-fly zones, privacy zones, and landing zones.
2. Operator creates a patrol template for perimeter, grid, or adaptive routing.
3. Backend generates a route preview and validates every waypoint before mission creation.
4. Sensor events are stored and validated. They can create incidents or proposed mission runs, but cannot directly command drone movement.
5. Mission runs use strict states and operator actions: approve, pause, resume, abort, return home.

## Backend

- API: `backend/modules/property_patrol/api.py`
- Models: `backend/modules/property_patrol/models.py`
- Schemas: `backend/modules/property_patrol/schemas.py`
- Services:
  - `route_planner.py`: reuses existing patrol perimeter/grid planning.
  - `policy.py`: safe-area/no-fly/privacy/mission parameter validation.
  - `preflight.py`: route, battery, GPS, telemetry, connection extension checks.
  - `sensor_events.py`: freshness, confidence, duplicate, and location validation.
  - `state_machine.py`: strict mission transitions.
  - `dispatch.py`: validated dispatch boundary for existing drone runtime integration.

## Frontend

- Page: `/dashboard/property-patrol`
- API client: `frontend/src/modules/property-patrol/api/propertyPatrolApi.ts`
- Compatibility route: `/dashboard/privatepatrol` still works, with user-facing labels renamed.

## API Endpoints

- `GET/POST /api/property-patrol/sites`
- `GET/PATCH/DELETE /api/property-patrol/sites/{site_id}`
- `GET/POST /api/property-patrol/templates`
- `GET/PATCH/DELETE /api/property-patrol/templates/{template_id}`
- `POST /api/property-patrol/route-preview`
- `POST /api/property-patrol/missions/validate`
- `POST /api/property-patrol/missions/start`
- `POST /api/property-patrol/missions/{id}/approve`
- `POST /api/property-patrol/missions/{id}/pause`
- `POST /api/property-patrol/missions/{id}/resume`
- `POST /api/property-patrol/missions/{id}/abort`
- `POST /api/property-patrol/missions/{id}/return-home`
- `GET /api/property-patrol/missions`
- `GET /api/property-patrol/missions/{id}`
- `POST/GET /api/property-patrol/sensor-events`
- `GET/POST /api/property-patrol/incidents`
- `GET/PATCH /api/property-patrol/incidents/{id}`
- `POST /api/property-patrol/incidents/{id}/acknowledge`
- `POST /api/property-patrol/incidents/{id}/mark-false-positive`
- `POST /api/property-patrol/incidents/{id}/close`

## State Machine

Main flow:

`DRAFT -> VALIDATED -> PREFLIGHT_CHECK -> ARMED -> TAKEOFF -> PATROL -> RETURN_HOME -> LANDING -> COMPLETED`

Terminal/error states include `ABORTED`, `FAILED`, `GEOFENCE_VIOLATION`, `LOW_BATTERY_RTH`, `LINK_LOST_RTH`, `AIRSPACE_BLOCKED`, and `SENSOR_TRIGGER_REJECTED`.

## Sensor Trigger Flow

Sensor request:

```json
{
  "site_id": 1,
  "sensor_id": "gate_camera_01",
  "external_event_id": "evt_20260611_001",
  "event_type": "possible_intrusion",
  "confidence": 0.84,
  "zone_id": "north_gate",
  "timestamp": "2026-06-11T14:10:00Z",
  "approx_location": { "lat": 50.123, "lon": 5.123 },
  "evidence_clip_id": "clip_123"
}
```

Outcomes:

- Invalid, duplicate, old, low-confidence, or outside-site events are rejected.
- `notify_only` creates an incident only.
- `approval_required` creates an incident and proposed mission run.
- `auto_dispatch` still requires route policy and preflight success.

## Safety And Privacy Rules

- Routes must stay inside `flight_safe_area`.
- Routes must avoid `no_fly_zones`.
- Sensor coordinates are never used as direct drone commands.
- Auto-dispatch warns in UI and is still backend-gated.
- Privacy settings are first-class template fields: face blur, license-plate blur, event clip only, retention, and camera direction.
- No face recognition, identity inference, or automatic person following is implemented.

## Testing

Backend:

```bash
.venv/bin/pytest backend/tests/test_property_patrol.py
```

Frontend:

```bash
cd frontend
npm run build
```

Migration:

```bash
cd backend
../.venv/bin/alembic upgrade head
```

## Known Limitations

- Real MAVLink/ROS mission upload is behind a dispatch boundary and must be wired to the selected runtime/SITL profile before real flight.
- Live Property Patrol Mission websocket events are not yet published; the page reads REST state.
- Site geometry is stored as JSON GeoJSON rather than indexed PostGIS columns.
- The management page includes a sample polygon path; full drawing UX can reuse existing TerraDraw components from the private patrol and fields modules.

