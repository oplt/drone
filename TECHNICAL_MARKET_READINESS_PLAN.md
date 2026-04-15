# Technical Market Readiness Plan

## 1. What the app is today
- A full-stack drone operations platform that combines mission planning, preflight, autonomous mission execution, live telemetry/video, alerting, photogrammetry, warehouse workflows, private patrol, and animal monitoring in one product surface.
- Evidence from repo:
  - Product scope is described in `README.md`.
  - FastAPI runtime entrypoint is `backend/api/api_main.py`.
  - Core flight/runtime orchestration lives in `backend/drone/orchestrator.py`.
  - Mission APIs are concentrated in `backend/api/routes/routes_flights.py`.
  - Mapping pipeline spans `backend/api/routes/routes_mapping.py`, `backend/services/photogrammetry/service.py`, and `backend/tasks/photogrammetry_tasks.py`.
  - React operator console lives under `frontend/src/` with major operational tabs in `frontend/src/pages/dashboard/tabs/`.
- Current architecture summary:
  - Backend is a modular monolith in Python/FastAPI with a large central orchestrator, PostgreSQL via async SQLAlchemy, WebSocket fan-out, Celery + Redis for photogrammetry, and local filesystem-backed asset storage.
  - Frontend is React 19 + TypeScript + Vite + MUI with TanStack Query, Google Maps, and Cesium.
  - The codebase is actively moving toward an orchestrator-owned runtime envelope model, documented in `docs/adr/ADR-001-canonical-live-ops-runtime-architecture.md`, but the implementation is still transitional.
- Current maturity level:
  - **MVP with some early-production foundations.**
  - It is beyond a prototype because it has persistence, auth, restart recovery, background workers, ADRs, queue resilience tests, and multiple operational surfaces.
  - It is not yet a credible growth-stage foundation because deployment, security posture, tenanting, observability, and enterprise controls are still incomplete.

## 2. Technical strengths already present
- The product already has a serious operational core instead of a toy CRUD app. `backend/drone/orchestrator.py`, `backend/flight/`, `backend/runtime/`, and `backend/api/routes/routes_flights.py` show real mission-state, telemetry, lifecycle, and recovery concerns.
- There is evidence of architecture thinking, not just code accumulation. `docs/adr/ADR-001-canonical-live-ops-runtime-architecture.md` and `docs/architecture/live-ops-hot-path-current-state.md` accurately describe current runtime problems and the intended direction.
- The backend has durable mission runtime, command audit, and preflight repositories in `backend/db/repository/mission_runtime_repo.py`, `operator_command_repo.py`, and `preflight_run_repo.py`. That is unusually good for an MVP in this category.
- Photogrammetry is already separated from the API process with a Celery queue, worker settings, and explicit deployment notes in `backend/tasks/README.md`. That is a sound foundation for heavy compute workloads.
- Telemetry persistence and replay optimization are not an afterthought. `backend/db/models.py` includes `TelemetrySummary` and multiple indexes; `backend/tests/bench/test_telemetry_perf.py` benchmarks replay and summary reads.
- There is some resilience engineering in the hot path. `backend/tests/test_queue_resilience.py` verifies queue overflow behavior and non-blocking control-path semantics.
- The frontend is typed and operationally broad. The dashboard already exposes mission creation, telemetry, mapping, analytics, settings, warehouse, private patrol, and livestock workflows rather than a single demo page.

## 3. Technical weaknesses and production risks
- Fragile areas:
  - Runtime ownership is still split across orchestrator, websocket manager, alert engine, and route layer. The repo itself documents this in `docs/architecture/live-ops-hot-path-current-state.md`.
  - `backend/api/routes/routes_flights.py` is very large and still acts as a major orchestration boundary, which will slow change velocity and increase regression risk.
  - The orchestrator is a single high-blast-radius object with transport, lifecycle, event fan-out, batching, telemetry ingest, and some integration concerns combined in one class.
- Scale risks:
  - WebSocket fan-out is single-process and in-memory in `backend/messaging/websocket.py`; there is no shared pub/sub layer or horizontal fan-out strategy.
  - Telemetry ingest is still thread-based inside the API process in `backend/drone/orchestrator.py`.
  - Analytics endpoints such as `backend/api/routes/routes_analytics.py` still do substantial Python-side aggregation and repeated DB reads instead of leaning on prebuilt read models.
  - Mapping assets are served from local disk in `backend/api/api_main.py` and signed from filesystem paths in `backend/services/photogrammetry/asset_gateway.py`; this does not scale cleanly to multiple app instances.
- Security risks:
  - Real secrets and credentials are committed in `backend/.env` and `frontend/.env`, including DB credentials, JWT secret, Google Maps keys, Cesium token, Raspberry Pi password, and vault key. This is an immediate credibility and operational risk.
  - JWT auth is basic: access-token only, no refresh tokens, no revocation, no session management, no MFA, and no real RBAC beyond admin email/domain checks in `backend/auth/deps.py`.
  - Frontend tokens are stored in `localStorage` via `frontend/src/auth.tsx`, increasing blast radius for XSS.
  - WebSocket auth supports query-string tokens in `backend/api/routes/routes_websocket.py`, which increases token leakage risk via logs/proxies.
  - `backend/api/api_main.py` exposes `/debug/routes` unguarded.
  - Asset signing falls back to `settings.jwt_secret` in `backend/services/photogrammetry/asset_gateway.py`, which couples unrelated secrets.
- Maintainability risks:
  - Several major frontend tabs are extremely large, stateful pages under `frontend/src/pages/dashboard/tabs/`, which will become expensive to evolve.
  - Fetch logic is inconsistent: some areas use TanStack Query, while others use ad hoc `fetch` patterns and manual intervals.
  - There is no visible backend package lock, Docker baseline, or CI pipeline in the repo root.
- Operational risks:
  - Database schema management is mixed. Alembic exists, but `backend/db/session.py` also runs `Base.metadata.create_all()` at startup.
  - There is no deployment manifest, infra-as-code, health-depth checks, backup automation, runbook structure, or environment promotion story in the repo.
  - Logging is file-based local disk logging in `backend/config.py`; there is no structured centralized observability pipeline.
- UX/performance risks:
  - The app covers many verticals at once, but the trust signals for serious customers are weaker than the feature count.
  - Live mission UX depends on a hybrid of polling and websocket state (`frontend/src/hooks/useMissionStatusPolling.tsx` and `useTelemetryWebsocket.ts`), which can feel inconsistent under load or disconnects.
  - Large MUI pages with Cesium/Google Maps and manual state handling will be hard to keep responsive on lower-end operator hardware.

## 4. Market-facing technical expectations
- In this category, users will expect:
  - Fast mission planning and near-real-time live ops.
  - Reliable telemetry continuity and reconnect behavior.
  - Strong asset security and controlled sharing.
  - Simple onboarding for teams, sites, vehicles, and operators.
  - Exportable mission data, imagery, logs, and mapping outputs.
  - Multi-user collaboration with roles and org/project boundaries.
  - Auditability for flight activity, operator commands, alerts, and changes.
  - Integration hooks for GIS, storage, enterprise identity, and downstream systems.
  - A deployment story that feels safe for serious field operations.
- What buyers will use to compare products:
  - Whether the product supports organizations/projects/sites/fleets cleanly.
  - Whether it has SSO, roles, audit logs, and export controls.
  - Whether it has APIs/webhooks and integration readiness.
  - Whether mapping assets, telemetry history, and media can be shared safely.
  - Whether operations continue cleanly across failures, reconnects, and restarts.
- What technical signals increase trust:
  - Explicit org/workspace isolation.
  - Role-based permissions and audit trails.
  - Signed asset delivery, retention controls, and data portability.
  - Observable system health, queue depth, and job status.
  - Import/export, backups, and webhook/API surfaces.
- What missing signals reduce confidence:
  - Committed secrets.
  - No visible CI/CD or deployment baseline.
  - No enterprise auth story.
  - No tenant model.
  - No customer-visible audit/event history for flights, settings, and assets.
- Official competitor/market evidence:
  - DroneDeploy publicly emphasizes SAML SSO, role types, and exportable audit logs: https://www.dronedeploy.com/product/security
  - Pix4Dcloud publicly highlights teams access control, API access, webhooks, SSO, custom integrations, and custom storage at higher tiers: https://www.pix4d.com/product/pix4dinspect-inspection-asset-management-software
  - Drone Harmony publicly promotes API/webhooks, telemetry/video access, and partner integration surfaces: https://www.droneharmony.com/api
  - Esri Site Scan documents organization/project/mission/flight hierarchy and enterprise export/publish workflows: https://doc.arcgis.com/en/site-scan/latest/get-started/organizational-structure.htm

## 5. Competitiveness gaps
| gap | why it matters | customer-visible or internal | likely competitor benchmark | business consequence if ignored |
|---|---|---|---|---|
| No real org/workspace/tenant model | Serious buyers need account boundaries, team ownership, and data segregation | Customer-visible | Site Scan organization/project hierarchy; DroneDeploy enterprise org roles | Weakens enterprise and multi-site sales immediately |
| Basic auth without SSO/RBAC/session controls | Security and IT buyers expect enterprise identity and scoped permissions | Customer-visible | DroneDeploy SAML + roles; Pix4D enterprise SSO + team controls | Security review friction and slower deal cycles |
| Secrets committed in repo and env handling is unsafe | Undermines security credibility and raises actual incident risk | Internal with major customer impact | Competitors signal mature security posture | Can kill trust in diligence or pilot discussions |
| Local-disk asset storage and single-instance assumptions | Limits scaling, HA, and controlled asset delivery | Internal and customer-visible | Object storage + signed delivery + retention controls | Reliability issues as jobs and customers grow |
| Split live-state model between polling, websocket cache, and route state | Causes inconsistent operator experience and harder incident debugging | Customer-visible | Unified live ops event stream and stable runtime state | Live missions feel less dependable than alternatives |
| No customer-facing audit timeline for missions/settings/assets | Buyers need traceability and operator accountability | Customer-visible | Audit activity logs and flight histories | Higher support cost and lower compliance confidence |
| No webhooks/public API strategy beyond internal endpoints | Integrations reduce switching risk and expand deal size | Customer-visible | Drone Harmony API; Pix4D API/webhooks | Harder to land platform or partner-led deals |
| No CI/CD, container baseline, or production deployment contract | Slows reliable release cadence and operational repeatability | Internal | Competitors ship as managed SaaS or hardened enterprise deployment | More incidents, slower roadmap execution |
| Limited observability beyond local logs and ad hoc metrics | Hard to run real operations and support customers | Internal | Centralized logs, traces, job metrics, alerting | Support becomes expensive and reactive |
| Product scope is broad but vertical depth signals are uneven | Breadth without trust features reads as unfinished | Customer-visible | Competitors feel narrower but more complete | Prospects may choose safer-looking incumbents |

## 6. Recommended technical improvements
| recommendation | exact problem solved | customer impact | competitive necessity | revenue influence | risk reduction | effort | fit with current stack | recommendation priority |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Add org/workspace/project model with scoped ownership | Replaces single-user assumptions and prepares data isolation, shared operations, and fleet ownership | 5 | 5 | 5 | 4 | 4 | 5 | P1 |
| Implement RBAC + SSO-ready auth/session architecture | Fixes basic auth posture and enables admin/operator/viewer roles, enterprise login, and safer sessions | 5 | 5 | 5 | 5 | 4 | 4 | P1 |
| Complete the orchestrator-owned live runtime path | Removes split state between websocket cache, polling, route globals, and partial event ownership | 5 | 5 | 4 | 5 | 4 | 5 | P1 |
| Move mapping/media assets to object storage with signed URLs and retention policies | Replaces local-disk delivery and supports multi-instance deployment, safer sharing, and lifecycle management | 4 | 4 | 4 | 4 | 3 | 4 | P1 |
| Build customer-visible mission activity timeline and audit log | Turns backend command/preflight/runtime history into a trust feature | 5 | 4 | 4 | 4 | 2 | 5 | P1 |
| Establish production deployment baseline: Docker, CI, staged envs, migrations-only schema changes | Fixes release reliability, repeatability, and environment drift | 4 | 4 | 4 | 5 | 3 | 5 | P1 |
| Add centralized observability: structured logs, metrics, tracing, job/queue dashboards, alerting | Makes incidents diagnosable and proves operational discipline | 4 | 4 | 4 | 5 | 3 | 4 | P1 |
| Add import/export package for flights, telemetry, imagery metadata, mapping outputs, and settings | Lowers switching risk and gives buyers confidence in data portability | 4 | 4 | 5 | 3 | 3 | 4 | P2 |
| Introduce public API + outbound webhooks for mission/job/alert events | Makes the platform integratable and sellable into larger workflows | 4 | 5 | 5 | 3 | 3 | 4 | P2 |
| Harden security baseline: secret rotation, env cleanup, token redesign, debug endpoint removal, asset-signing secret split | Fixes the most credibility-damaging security problems | 5 | 5 | 5 | 5 | 2 | 5 | P1 |
| Build admin/support console for fleets, users, jobs, runtime health, and stuck missions | Lowers support cost and increases operational confidence | 4 | 3 | 4 | 4 | 3 | 5 | P2 |
| Add read-model caching for analytics, replay, and dashboard summaries | Improves perceived responsiveness and lowers query cost | 4 | 3 | 3 | 4 | 3 | 4 | P2 |

## 7. Customer-convincing feature additions
For each top feature:

### 1. Mission Audit Timeline
- Feature name: Mission Audit Timeline
- User/buyer concern it addresses: “Can I trust what happened during a flight, who changed it, and why it failed?”
- Why it helps win customers: It converts backend lifecycle and operator-command persistence into a visible trust signal during pilots, ops reviews, and incident follow-up.
- Minimum viable implementation: Unified timeline UI combining mission state changes, preflight results, operator commands, alerts, video/telemetry health, and photogrammetry job transitions for a flight.
- Dependency on technical foundations: Mission runtime repo, operator command repo, preflight repo, and runtime envelopes already exist.
- Success metric: % of flights with complete timelines; reduction in support time-to-diagnose; timeline adoption during pilot reviews.

### 2. Organization, Fleet, and Project Management
- Feature name: Org / Fleet / Project Management
- User/buyer concern it addresses: “Can multiple teams, sites, vehicles, and customers use this safely?”
- Why it helps win customers: It makes the product look like a platform instead of a single-console tool.
- Minimum viable implementation: Organizations, projects, vehicles, operator memberships, and per-project mission/data ownership; basic admin/operator/viewer roles.
- Dependency on technical foundations: Requires schema updates, scoped auth, and API ownership changes.
- Success metric: number of multi-user accounts; number of vehicles per org; pilot-to-paid conversion for team accounts.

### 3. Secure Enterprise Access
- Feature name: Secure Enterprise Access
- User/buyer concern it addresses: “Will our IT/security team approve this?”
- Why it helps win customers: SSO and RBAC shorten security reviews and reduce friction with larger customers.
- Minimum viable implementation: OIDC/SAML-ready auth abstraction, role model, short-lived access tokens + refresh/session records, admin audit of sign-ins.
- Dependency on technical foundations: Auth/session redesign and org model.
- Success metric: time to complete security review; % of enterprise accounts using SSO; reduced auth-related support issues.

### 4. Data Portability and Customer Export Packs
- Feature name: Export Packs and Portability
- User/buyer concern it addresses: “Can we get our data out if we adopt this?”
- Why it helps win customers: Reduces switching risk and strengthens trust during procurement.
- Minimum viable implementation: Export ZIP/package containing mission manifest, flight logs, telemetry CSV/JSON, mapping asset links, field boundaries, alerts, and operator actions.
- Dependency on technical foundations: Audit timeline, object storage, and stable asset metadata.
- Success metric: export usage; sales objections reduced around lock-in; faster onboarding from competitor migrations.

### 5. Operational Health and Incident Dashboard
- Feature name: Ops Health Dashboard
- User/buyer concern it addresses: “Is the system safe and dependable enough for field operations?”
- Why it helps win customers: Makes runtime reliability visible and gives operators confidence before and during live use.
- Minimum viable implementation: Fleet/job/runtime health page with telemetry connection state, queue depth, worker availability, job lag, recent failures, and per-service health.
- Dependency on technical foundations: Centralized metrics and structured events.
- Success metric: MTTR reduction; fewer “unknown failure” tickets; better pilot NPS from operators.

## 8. Minimum credible production architecture
Describe:

- App architecture:
  - Keep the modular monolith.
  - Make the orchestrator-owned runtime envelope path the single live-ops contract.
  - Move route modules back to HTTP orchestration and validation only.
  - Split large route/service files by domain boundary: mission control, mapping, fleet/admin, patrol, warehouse.
- Data layer:
  - PostgreSQL remains the system of record.
  - Use Alembic-only schema evolution in production; stop using `create_all()` on startup.
  - Add org/project/vehicle ownership tables and scoped foreign keys.
  - Maintain append-only audit/event tables for operator actions and mission lifecycle.
- Auth/permissions:
  - OIDC/SAML-ready identity layer with local auth fallback.
  - Access token + refresh/session storage.
  - Role model at org/project scope: org admin, operations manager, pilot/operator, viewer/auditor.
  - Remove email/domain-based admin checks as the primary permission model.
- Background processing:
  - Keep Celery + Redis for photogrammetry and future long-running jobs.
  - Add dead-letter/retry visibility and admin requeue actions.
  - Expand worker model to support ingest, export pack generation, and heavy analytics rebuilds if needed.
- Caching:
  - Redis for ephemeral runtime cache, websocket pub/sub fan-out if multiple app instances are introduced, and dashboard read-model caching.
  - Keep DB as source of truth.
- Observability:
  - Structured JSON logs.
  - Metrics for telemetry ingest rate, websocket clients, queue depths, batch flush latency, worker job age, photogrammetry progress, and API latency.
  - Tracing for auth, mission start, preflight, telemetry ingest, mapping job lifecycle, and asset delivery.
  - Error reporting for frontend and backend.
- Security baseline:
  - Remove committed secrets and rotate all exposed credentials immediately.
  - Separate JWT secret, asset signing secret, and vault key.
  - Use env or secret manager only.
  - Add CSP/XSS review for frontend, httpOnly secure refresh/session cookies if auth model allows, and remove query-string tokens where possible.
  - Protect debug/admin endpoints and add permission checks consistently.
- Deployment approach:
  - Containerize API, worker, and Redis dependencies.
  - Run API as stateless service instances behind a load balancer.
  - Use object storage for assets and recordings.
  - Use managed Postgres and managed Redis where possible.
  - Maintain dev/staging/prod environments with automated migrations.
- Testing approach:
  - Keep queue/hot-path backend tests.
  - Add API contract tests for auth, mission lifecycle, mapping job lifecycle, and asset access.
  - Add frontend smoke/e2e tests for sign-in, mission launch, telemetry page, and mapping status.
  - Add failure-mode tests for reconnects, worker loss, expired tokens, and partial mapping failures.
- Failure/retry strategy:
  - Runtime envelopes stay best-effort for high-frequency telemetry but durable for mission lifecycle and operator actions.
  - Worker jobs use explicit retries with idempotent transitions.
  - Mission runtime recovers from interrupted state on restart, extending the current `backend/flight/restart_recovery.py` pattern.
  - Failed exports, mapping jobs, and notifications are retryable from admin/support surfaces.

## 9. Technical roadmap
Break into:

### Now (0-30 days)
- Rotate and remove all committed secrets; replace tracked `.env` values with examples only.
  - Why it belongs there: It is the highest-risk credibility issue.
  - Dependency notes: None.
  - Expected impact: Immediate security risk reduction and better diligence posture.
- Establish a production baseline: Dockerfiles, compose/dev stack, CI for lint/test/build, Alembic-only migration path.
  - Why it belongs there: Release reliability and repeatability are foundational.
  - Dependency notes: Light backend/frontend packaging work.
  - Expected impact: Faster, safer delivery and easier staging/prod setup.
- Finish unifying live mission state under orchestrator + mission runtime repository and reduce route-layer ownership.
  - Why it belongs there: It fixes the most important operational inconsistency.
  - Dependency notes: Builds directly on current ADR direction and existing repos.
  - Expected impact: More reliable live ops and simpler debugging.
- Add structured logging, metrics, and runtime/job health dashboards.
  - Why it belongs there: Supportability is currently too weak.
  - Dependency notes: Best done before scaling feature breadth.
  - Expected impact: Lower MTTR and higher operator confidence.
- Ship a visible mission timeline/audit screen using existing persisted data.
  - Why it belongs there: Fastest customer-visible trust win.
  - Dependency notes: Uses current command/preflight/runtime persistence.
  - Expected impact: Better demo value and easier incident review.

### Next (30-60 days)
- Introduce organizations/projects/vehicles and scoped ownership.
  - Why it belongs there: It is required for serious customer adoption but needs careful schema/API/UI work.
  - Dependency notes: Should follow auth/session redesign planning.
  - Expected impact: Unlocks team accounts and enterprise conversations.
- Redesign auth into sessions + RBAC + SSO-ready abstraction.
  - Why it belongs there: Critical for IT acceptance and access control.
  - Dependency notes: Strongly coupled to org/project scope.
  - Expected impact: Better enterprise fit and lower security-review friction.
- Move mapping and media assets to object storage with signed delivery and retention rules.
  - Why it belongs there: Required before multi-instance deployment and bigger jobs.
  - Dependency notes: Deployment baseline first; storage abstraction second.
  - Expected impact: Better scalability, sharing, and reliability.
- Build export packs and customer data portability flows.
  - Why it belongs there: Strong sales tool once asset storage and audit metadata are cleaner.
  - Dependency notes: Benefits from audit timeline and object storage.
  - Expected impact: Lower switching-risk objections.
- Add admin/support console for users, fleets, jobs, and stuck missions.
  - Why it belongs there: Helps operations scale without heroics.
  - Dependency notes: Requires observability and org ownership context.
  - Expected impact: Lower support cost.

### Later (60-120 days)
- Add public API and outbound webhooks for mission/job/alert events.
  - Why it belongs there: Valuable but strongest after auth, org model, and audit boundaries stabilize.
  - Dependency notes: Needs permission model, idempotency, and event contracts.
  - Expected impact: Better integration and platform sales potential.
- Add fleet-level compliance/trust features: retention controls, operator certification metadata, device readiness records, evidence bundles.
  - Why it belongs there: Strong enterprise differentiators after core platform hardening.
  - Dependency notes: Builds on audit, org, and admin foundations.
  - Expected impact: Stronger enterprise positioning.
- Build richer analytics/read models and performance optimizations for large fleets.
  - Why it belongs there: Important for growth but not before core trust features.
  - Dependency notes: Depends on production telemetry/event architecture stability.
  - Expected impact: Better large-account usability.
- Add partner integration templates for GIS/cloud storage/work-order systems.
  - Why it belongs there: Best after API/webhooks are available.
  - Dependency notes: Requires external API maturity.
  - Expected impact: Deal expansion and stickiness.

## 10. Not worth doing yet
- Full microservices decomposition.
  - Why: The repo is explicitly best served by a modular monolith today, and splitting it now would add operational burden without solving its main trust gaps.
- Kubernetes-first platform engineering.
  - Why: The app needs a clean container and deployment baseline first; orchestration complexity would be infrastructure theater.
- Custom event bus or Kafka adoption.
  - Why: The internal runtime envelope pattern is not yet fully stabilized; Redis + in-process contracts are enough for the next phase.
- Offline-first operator console.
  - Why: Valuable in some field contexts, but lower leverage than live-state correctness, auditability, and secure deployment.
- Broad new vertical modules beyond current scope.
  - Why: The product already spans agronomy, warehouse, patrol, and livestock. More breadth will dilute execution unless the core platform becomes more trustworthy first.

## 11. Final recommendation
Answer clearly:

- Can this app become technically strong enough to compete?
  - Yes, but only if the next phase prioritizes trust architecture over adding more surface area. The codebase already has enough real functionality and enough partial foundations to become credible.
- What are the most important technical upgrades?
  - 1. Security cleanup and auth redesign.
  - 2. Organization/project/vehicle ownership model.
  - 3. Completion of the orchestrator-owned live runtime architecture.
  - 4. Production deployment + observability baseline.
  - 5. Object storage + signed asset delivery.
- What extra features would most help convince customers to choose it?
  - 1. Mission audit timeline and exportable activity logs.
  - 2. Team/org management with scoped roles.
  - 3. Secure SSO-ready enterprise access.
  - 4. Data portability/export packs.
  - 5. Ops health dashboard for fleets, jobs, and live runtime.
- What should be built first, second, and third?
  - First: security cleanup + production baseline + live runtime unification.
  - Second: mission audit timeline + observability + admin/support health tooling.
  - Third: org/project/RBAC/SSO + object storage + export/API foundations.
