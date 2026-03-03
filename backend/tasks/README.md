# Photogrammetry Worker Deployment

Photogrammetry is CPU/GPU heavy and must not run inside the API container.

## Recommended topology

- `api` container: FastAPI only (enqueue jobs, serve status/routes).
- `redis` container/service: Celery broker/result backend.
- `photogrammetry-worker` node(s): Celery workers running `photogrammetry` queue.
- Optional: dedicated GPU workers for mesh-heavy workloads.

## Environment variables

- `CELERY_BROKER_URL` (example: `redis://redis:6379/0`)
- `CELERY_RESULT_BACKEND` (example: `redis://redis:6379/0`)
- `CELERY_PHOTOGRAMMETRY_QUEUE` (default: `photogrammetry`)
- `MAPPING_JOB_QUEUE_BACKEND` (must be `celery`)
- `WEBODM_BASE_URL` (example: `http://webodm:8001`)
- `WEBODM_API_TOKEN` (JWT token from WebODM)
- `WEBODM_PROJECT_ID` (target project id in WebODM)
- `PHOTOGRAMMETRY_INPUTS_DIR` (shared input mount for uploaded/drone-sync images)
- `PHOTOGRAMMETRY_STORAGE_DIR` (shared output mount for published assets)
- `PHOTOGRAMMETRY_DRONE_SYNC_DIR` (optional source root for direct drone sync mode)
- `PHOTOGRAMMETRY_3DTILES_CMD` (required in production; command template with `{input_gltf}` and `{output_dir}`)

## Run worker

```bash
celery -A backend.tasks.celery_app:celery_app worker \
  --loglevel=INFO \
  --queues=photogrammetry \
  --hostname=photogrammetry@%h
```

## Autoscale example

```bash
celery -A backend.tasks.celery_app:celery_app worker \
  --loglevel=INFO \
  --queues=photogrammetry \
  --autoscale=8,1
```

Scale horizontally by adding more worker nodes bound to the `photogrammetry` queue.

## Required worker toolchain

- `gdal_translate` (COG conversion)
- `gdal2tiles` or `gdal2tiles.py` (XYZ tiles generation when enabled)
- mesh converter: `obj2gltf` or `assimp` (if WebODM output is not already GLB/GLTF)
- 3D tiler command defined in `PHOTOGRAMMETRY_3DTILES_CMD`

Without these binaries, jobs fail fast by design so missing production dependencies are visible immediately.
