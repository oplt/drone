# Agriculture Flight and Field Media Analysis Roadmap

This document is the documentation index for the full implementation backlog in [`tasks.txt`](../tasks.txt). The complete evidence, gap matrix, phased roadmap, task specifications, acceptance criteria and next-action order are maintained there because the requested final planning artifact is `tasks.txt`.

Audit date: 2026-08-03. Repository: `/home/polat/Desktop/Projects/drone_app`.

## 1. Executive summary

The repository has a substantial agriculture backend foundation but not a complete professional agriculture survey product. Field-linked flights, immutable profile/input snapshots, telemetry, media manifests, resumable uploads, frame lineage, analysis runs, observations/evidence, sensor fusion, temporal review, actions, exports, audit records, Celery stages and model-governance contracts are present. The frontend exposes many of these capabilities through React Query and review panels.

The principal mismatch is workflow depth: the backend is ahead of the frontend. The agriculture planner is still a handoff to the generic field-survey page; there is no complete agriculture grid/exclusion editor, blocking safety checklist, agriculture-specific live control/event/recovery surface, post-flight inventory workflow, or synchronized video/map/telemetry analysis workspace. Existing RGB analysis contains useful quality and visible-proxy heuristics, but validated crop-specific models and scientifically bounded claims are not proven.

The recommended sequence is contract verification, frontend exposure of existing backend capabilities, safe flight execution, reliable media processing, validated RGB analysis, spatial/video/reporting features, advanced sensors, and production hardening.

## 2. Current architecture

Backend evidence is concentrated in `backend/modules/agriculture/` (`api.py`, `service.py`, `models.py`, `contracts.py`, `schemas.py`, `policy.py`, `quality.py`, `storage.py`, `georeferencing.py`, `aggregation.py`, `heuristics.py`, `crop_insights.py`, `fusion.py`, `temporal_models.py`, `evaluation.py`, `release_governance.py`, and worker/operations modules). Mission integration is in `backend/modules/missions/service/mission_create.py` and `mission_start.py`; video integration is in `backend/modules/video_analysis/service/pipeline.py`, `detector.py` and `geo.py`.

Core relationships are `Field → AgricultureFieldProfile → AgricultureFlight → telemetry/media → frame lineage → analysis run/stages → observations/evidence/layers → review, comparison, action and export`. Sensor calibration/bands/readings/fusion, crop insights, temporal review, datasets and model governance attach to these records.

Frontend routes are defined in `frontend/src/app/routes/AppRouter.tsx` for agriculture fields, field detail, flight detail and analysis runs. The module is under `frontend/src/modules/agriculture/`, including field/profile/planner/preflight/live-status, quality/coverage, map/review/evidence/timeline, sensor/temporal, action/export and governance components. `api.ts`, `hooks.ts`, `types.ts` and `runtime.ts` provide the client boundary. The frontend has strong review scaffolding but no complete agriculture video player or dedicated flight-execution workflow.

The agriculture API includes field/profile, plan preview/start, flight quality/coverage/timeline, telemetry, manifests/media, resumable uploads, frame finalization, analysis runs, observations/evidence/review, sensor fusion, crop risks/growth/yield, temporal comparisons, actions/prescriptions/exports, datasets and governance. Structured agriculture events currently log through `events.py`; generic mission WebSocket infrastructure exists, but an agriculture-specific durable sequence/replay contract is not established.

## 3. Current end-to-end workflow

| Stage | Assessment |
|---|---|
| Field selection/profile | Complete foundation; boundary editing, exclusions and full agronomic metadata are partial. |
| Planning/grid | Partial; backend preview/presets exist, frontend dedicated planner/editor is missing. |
| Pre-flight | Partial; panel and policy/readiness exist, but one blocking auditable checklist is incomplete. |
| Execution | Partial/backend-led; telemetry and generic runtime exist, agriculture controls/recovery/live synchronization are incomplete. |
| Capture/upload | Partial; manifests, checksums, chunks and lineage exist, but camera integration, reconciliation and browser recovery need work. |
| Processing | Partial/backend-only; Celery stages/retries/checkpoints exist, but durable stage UX, orthomosaic/tiles and complete video indexing are unverified. |
| AI analysis | Partial; deterministic RGB quality/row/soil/water/anomaly proxies and sensor contracts exist, validated production agriculture models are not proven. |
| Review/visualization | Partial; map/list/evidence/quality/sensor/temporal surfaces exist, but synchronized media and scalable layers are missing. |
| Reporting/actions | Partial; actions, prescriptions, exports and audits exist, but report builder and complete output workflow are incomplete. |

## 4. Backend-to-frontend gap matrix

The highest-impact gaps are:

| ID | Backend evidence | Frontend gap | Priority |
|---|---|---|---|
| GAP-01 | `POST /agriculture/flights/plan-preview`, presets, policy | `AgricultureFlightPlanner` is a generic-page handoff; no dedicated grid editor | Critical |
| GAP-02 | Profile, field geometry and mission grid validation | No complete boundary/exclusion/obstacle editor | Critical |
| GAP-03 | Readiness, policy, quality and sensor status | No unified blocking weather/device/GPS/battery/camera/permission sign-off | Critical |
| GAP-04 | Telemetry/advisory and generic runtime WebSocket | No agriculture pause/resume/RTH/abort/live event/recovery surface | Critical |
| GAP-05 | Media/lineage/chunk APIs | No full inventory, missing-area or resumable upload UX | Critical |
| GAP-06 | Celery stage tasks, retry/checkpoint/dead letter | Stage-level progress/remediation is limited to polling | High |
| GAP-07 | Video pipeline, frame lineage and observation evidence | No synchronized video-frame-map-telemetry workspace | Critical |
| GAP-08 | Observation/layer/temporal schemas | SVG/small GeoJSON review is not a scalable tiled analysis map | High |
| GAP-09 | Model evaluation, shadow/publish/rollback/drift APIs | No agriculture model governance client/admin surface | High |
| GAP-10 | Review/actions/prescriptions/exports/audits | No complete alert, assignment, report-builder and feedback workflow | High |
| GAP-11 | Local and S3 storage adapters | Production wiring, scan/quota/retention/restore evidence is incomplete | Critical |
| GAP-12 | Org/owner/audit fields | End-to-end tenant/role/negative-path frontend proof is incomplete | Critical |

For each gap’s exact files, endpoint, business impact, dependencies, complexity and testable acceptance criteria, see `AGRI-001` through `AGRI-014` in [`tasks.txt`](../tasks.txt).

## 5. Agriculture-flight gap analysis

Field setup has reusable PostGIS fields, area/centroid and profiles, but needs boundary import/draw/edit, exclusions, obstacles, zones, crop metadata completeness and revision audit. Planning has presets, profile snapshots and preview, but needs parameter editing, coverage estimates, battery/time, segmentation, takeoff/landing, terrain/wind/no-fly and replan semantics. Pre-flight needs server-evaluated freshness, weather, permissions, device, GPS, battery, storage, camera, calibration and model checks with signed acknowledgement. Execution needs a safety-authorized command/event protocol, live map/coverage/waypoint/camera state, warnings, pause/resume/RTH/abort, reconnect and recovery. Post-flight needs inventory reconciliation, quality/missing-area validation, upload recovery, processing exceptions and previous-flight comparison.

## 6. Video and image analysis gap analysis

Media manifests, checksums, resumable chunks, frame timestamps, telemetry neighbors, georeferencing and quality metrics are the right foundation. Missing or unverified pieces are deterministic keyframe/thumbnail indexing, full video timeline, orthomosaic/tile generation, production object storage wiring, media security scanning, viewport-scale spatial indexing, durable processing progress, model artifact verification, and complete human feedback-to-dataset lineage. Every observation should retain mission, flight, field, coordinate/CRS, timestamp, source media/frame, model/version, calibration, confidence/uncertainty, quality gate and result schema version.

## 7. Recommended analyses

RGB is credible for crop/row segmentation, canopy/bare-soil cover, validated stand/missing-plant detection, visible water/lodging/obstacle candidates and crop-specific visible symptom candidates with human review. Multispectral is required for NDVI/NDRE/GNDVI/SAVI and calibrated vigor/chlorophyll proxies. Thermal is required for canopy-temperature and thermal irrigation/stress candidates. LiDAR/depth is required for reliable structure/height/terrain/obstacle products. Temporal analysis is feasible for aligned repeat flights, growth/cover trends and persistent anomaly change maps. Disease, nutrient, yield, biomass and stress claims must be sensor-, crop-, calibration- and evaluation-scoped.

## 8. Visualization roadmap

Prioritize tiled coverage/health/confidence/mask layers, detection overlays, severity and zone KPIs, synchronized video/map/telemetry, frame evidence, before/after temporal comparison, alert/action maps, filterable observation tables, trend charts, crop-growth timelines, report snapshots and GeoJSON/CSV/image/PDF exports. Keep the existing accessible map/list fallback while adding viewport queries, clustering, lazy thumbnails and server-side aggregation for large fields.

## 9. Frontend feature roadmap

Finish the existing component boundaries—field profile, planner, quality, coverage, health layers, observation map/drawer, evidence carousel, flight timeline, run progress, sensor calibration, inspection actions and export approval—inside a coherent field → plan → pre-flight → live flight → upload/process → review → action/report flow. Add field management, dedicated planner, blocking pre-flight, live flight, post-flight processing, synchronized analysis, history/comparison, alert center, recommendations, report/export center and model settings. All surfaces need loading, empty, stale/offline, permission, retry, partial-result and success states plus WCAG 2.1 AA keyboard, focus, reduced-motion, touch-target and color-independent semantics.

## 10. Data and API direction

Add versioned plan snapshots, boundary revisions, exclusions/obstacles, pre-flight check snapshots, command/event envelopes with sequence/replay/idempotency, complete media capture metadata, deterministic frame extraction versions, artifact checksums, CRS/geometry precision, result schema versions, mandatory model/calibration/quality provenance, spatial tile/viewport contracts, review feedback/dataset links, export snapshots and signed artifact lifecycle metadata. Generate or contract-test frontend types against backend schemas and stabilize status/error enums.

## 11. Phases and next actions

* **Phase 0 complete:** verify contracts, remove mock API connections, preserve stable errors, prove route parity and cross-tenant rejection, and add reproducible OpenAPI/test evidence. Browser E2E remains CI-only because the local sandbox cannot bind Vite port 5173.
* Phase 1: expose existing backend capabilities, upload/progress, provenance, alerts, actions, exports and governance.
* Phase 2: complete field setup, planning, pre-flight, safe live execution/recovery, post-flight and history.
* Phase 3: validate high-value RGB analyses and human review.
* Phase 4: add tiled maps, synchronized media, temporal comparison, reports and exports.
* Phase 5: add calibrated multispectral, thermal, LiDAR and advanced agronomic intelligence.
* Phase 6: harden security, storage, queues, observability, performance, offline behavior, E2E and deployment.

Top implementation order: `AGRI-001 → AGRI-002 → AGRI-003 → AGRI-004 → AGRI-005 → AGRI-006 → AGRI-007 → AGRI-009 → AGRI-008 → AGRI-010/011 → AGRI-012 → AGRI-013/014`.

The full task backlog uses the required implementation template and concrete acceptance criteria in [`tasks.txt`](../tasks.txt).
