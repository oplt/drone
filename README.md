# Drone Operations Platform

Production-oriented drone mission orchestration and geospatial analytics platform for autonomous field operations, telemetry monitoring, photogrammetry workflows, and operational intelligence.

Built with FastAPI, React, PostgreSQL/PostGIS, Redis, Celery, and real-time telemetry infrastructure, the platform provides a browser-based operator console for planning, executing, monitoring, and reviewing autonomous drone missions.

The system is designed for:

- Agricultural field operations
- Photogrammetry workflows
- Infrastructure inspection
- Indoor warehouse navigation
- Geospatial data collection
- Telemetry-driven operational monitoring

---

## Core Capabilities

- Autonomous mission planning and execution
- Real-time telemetry streaming and websocket broadcasting
- Geospatial overlays, routing, and geofence management
- Photogrammetry job orchestration with WebODM integration
- Preflight safety validation and operational readiness checks
- Asset, mission, and fleet lifecycle management
- Asynchronous mapping and processing pipelines
- AI-assisted analytics and operational workflows

> Status: active development platform with production-oriented backend architecture and ongoing hardware and ML integration validation.

---

# Why This Platform Exists

Modern drone operations often require multiple disconnected systems for:

- Mission planning
- Telemetry monitoring
- Photogrammetry processing
- Geospatial visualization
- Fleet management
- Operational logging
- Asset delivery
- Mapping analytics

This platform centralizes those workflows into a single operational system designed for autonomous and semi-autonomous drone operations.

---

# Screenshots


---

# System Architecture

```text
React/Vite Operator Dashboard
            |
            | HTTP + WebSocket
            v
FastAPI Backend API Layer
            |
            +-- Mission orchestration
            +-- Telemetry runtime
            +-- Mapping services
            +-- Preflight validation
            +-- Warehouse workflows
            +-- Irrigation pipelines
            +-- Livestock monitoring
            +-- Alerting and integrations
            |
            +-- PostgreSQL/PostGIS
            +-- Redis + Celery workers
            +-- MinIO / S3 storage
            +-- Optional WebODM
            +-- MQTT / OPC UA
            +-- MAVLink drone runtime
```

Heavy mapping and photogrammetry workloads are executed asynchronously through Celery queues outside the API process.

---

# System Design Highlights

- Asynchronous FastAPI backend architecture
- Celery-based distributed task processing
- PostGIS-backed geospatial storage
- Real-time websocket telemetry broadcasting
- Queue-isolated photogrammetry workers
- Signed asset delivery pipeline
- Event-driven mission lifecycle management
- Containerized local development environment
- Modular service-oriented backend structure

---

# Key Features

## Mission Operations

- Waypoint missions
- Grid survey planning
- Controlled-flight workflows
- Mission lifecycle tracking
- Route previews and validation
- Fleet readiness management
- Manual control endpoints

## Telemetry and Monitoring

- Live telemetry streaming
- Websocket event broadcasting
- Operational health checks
- Alerting and webhook integrations
- Mission timeline visualization
- Runtime status tracking

## Mapping and Photogrammetry

- Photogrammetry job orchestration
- WebODM integration hooks
- Asset staging and signed downloads
- Field-model registry workflows
- Terrain-processing support
- Geospatial overlays and exports

## Agricultural Workflows

- Irrigation capture workflows
- Field management APIs
- Geofence management
- Agricultural imaging support
- ROS2-oriented imaging pipeline support

## Warehouse and Indoor Navigation

- Warehouse map management
- Indoor exploration workflows
- Dock and scanned-map support
- GPS-denied operational flows

## Infrastructure and Integrations

- MQTT integration
- OPC UA integration
- S3-compatible object storage
- Google OIDC hooks
- API key management
- Docker Compose deployment baseline

---

# Example Use Cases

- Agricultural field mapping
- Irrigation inspection
- Infrastructure surveying
- Indoor warehouse navigation
- Security patrol operations
- Terrain and route analysis
- Drone fleet monitoring
- Mapping and orthomosaic generation

---

# Tech Stack

| Area | Technology |
|---|---|
| Backend API | FastAPI, Starlette, Uvicorn |
| Data Layer | SQLAlchemy 2, PostgreSQL/PostGIS, Alembic |
| Background Jobs | Celery, Redis |
| Frontend | React, TypeScript, Vite, Material UI |
| Mapping & GIS | Google Maps, Cesium, MapLibre, Leaflet |
| Drone Runtime | DroneKit, pymavlink, MAVLink |
| Storage | MinIO, S3-compatible object storage |
| Messaging | MQTT, OPC UA, WebSockets |
| Computer Vision | OpenCV, NumPy |
| DevOps | Docker, Docker Compose |
| Quality Tooling | pytest, Ruff, mypy, ESLint |

---

# Repository Structure

```text
backend/
├── api/routes/          # FastAPI route groups
├── auth/                # Authentication and authorization
├── db/                  # Database models and repositories
├── alembic/             # Database migrations
├── drone/               # MAVLink and drone integrations
├── flight/              # Mission workflows and preflight checks
├── messaging/           # MQTT, OPC UA, websocket integrations
├── services/            # Domain services
├── tasks/               # Celery tasks and workers
├── tests/               # Backend tests
└── config.py            # Runtime settings

frontend/
├── src/                 # React dashboard application
├── package.json
├── Dockerfile
└── nginx.conf
```

---

# Quick Start

## Clone the Repository

```bash
git clone <repo-url>
cd <repo-name>
```

## Start the Full Stack

```bash
docker compose up --build
```

Open:

- Frontend: `http://localhost:8080`
- API: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`

---

# Local Development

## Backend Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Frontend Setup

```bash
cd frontend
npm install
cd ..
```

## Database Migrations

```bash
alembic -c backend/alembic.ini upgrade head
```

## Start Backend

```bash
uvicorn backend.entrypoints.api.app:app --reload --host 0.0.0.0 --port 8000
```

## Start Frontend

```bash
cd frontend
npm run dev
```

---

# Environment Variables

Create local environment files:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Important backend variables include:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL/PostGIS connection |
| `JWT_SECRET` | Authentication token signing |
| `REDIS_URL` | Redis runtime and Celery backend |
| `CELERY_BROKER_URL` | Celery broker |
| `WEBODM_*` | Photogrammetry integration |
| `MQTT_*` | MQTT configuration |
| `S3_*` | Object storage configuration |
| `GOOGLE_MAPS_API_KEY` | Maps integration |

Frontend variables include:

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend API URL |
| `VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY` | Google Maps API key |
| `VITE_CESIUM_ION_TOKEN` | Cesium token |

---

# API Overview

FastAPI automatically exposes OpenAPI documentation:

- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`

Main route groups include:

| Area | Routes |
|---|---|
| Auth | `/auth/*` |
| Missions | `/tasks/missions/*` |
| Telemetry | `/telemetry/*` |
| Mapping | `/mapping/*` |
| Warehouse | `/warehouse/*` |
| Irrigation | `/irrigation/*` |
| Livestock | `/livestock/*` |
| Alerts & Settings | `/api/alerts`, `/api/settings` |

---

# Current Capabilities

- Mission planning and execution
- Telemetry monitoring
- Geofence management
- Mapping job orchestration
- WebODM integration
- Warehouse exploration workflows
- Real-time operational dashboards

---

# Planned / Experimental

- Autonomous irrigation analytics
- AI anomaly detection
- ROS2 orchestration improvements
- Multi-drone coordination
- Edge AI inference pipelines
- Advanced geospatial analytics

---

# Security Notes

- Replace all development secrets before deployment
- Use HTTPS in production
- Store certificates and credentials outside the repository
- Validate flight safety in simulation before real hardware deployment
- Review CORS and authentication configuration before public exposure

---

# Known Limitations

- Some integrations require environment-specific validation
- Drone hardware integrations depend on MAVLink-compatible systems
- ROS2 workflows require target-environment validation
- WebODM and object-storage integrations require external services
- Demo assets and screenshots are not yet included

---

# License

License not yet documented.



