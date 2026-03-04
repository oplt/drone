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
- `CELERY_ENABLE_NATIVE_ASYNC_TASK` (set `1` only when worker uses an async-capable pool)
- `MAPPING_JOB_QUEUE_BACKEND` (must be `celery`)
- `WEBODM_BASE_URL` (example: `http://webodm:8001`)
- `WEBODM_API_TOKEN` (JWT token from WebODM)
- `WEBODM_PROJECT_ID` (target project id in WebODM)
- `WEBODM_HTTP_RETRY_ATTEMPTS` (retry attempts for transient WebODM HTTP calls; default `5`)
- `WEBODM_HTTP_RETRY_MIN_DELAY_S` (initial retry delay seconds; default `4`)
- `WEBODM_HTTP_RETRY_MAX_DELAY_S` (max retry delay seconds; default `60`)
- `WEBODM_HTTP_RETRY_BACKOFF_FACTOR` (retry exponential factor; default `2`)
- `WEBODM_UPLOAD_BATCH_SIZE` (max images per multipart upload request; default `256` to avoid exhausting file descriptors)
- `PHOTOGRAMMETRY_INPUTS_DIR` (shared input mount for uploaded/drone-sync images)
- `PHOTOGRAMMETRY_STORAGE_DIR` (shared output mount for published assets)
- `PHOTOGRAMMETRY_DRONE_SYNC_DIR` (optional source root for direct drone sync mode)
- `PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR` (optional hot-folder where companion sync drops fresh drone photos)
- `PHOTOGRAMMETRY_CAPTURE_SYNC_CMD` (optional command to trigger external transfer; supports `{flight_id}`, `{source_dir}`, `{session_dir}`, `{sync_root}`, `{staging_dir}`)
- `PHOTOGRAMMETRY_CAPTURE_SYNC_TIMEOUT_S` (timeout for external sync command; default `180`)
- `PHOTOGRAMMETRY_FLIGHT_SYNC_TIMEOUT_S` (wait timeout for post-flight image staging; default `120`)
- `PHOTOGRAMMETRY_FLIGHT_SYNC_POLL_S` (poll interval for post-flight image staging; default `2`)
- `PHOTOGRAMMETRY_FLIGHT_SYNC_MIN_IMAGES` (minimum expected staged photos; default `1`)
- `PHOTOGRAMMETRY_3DTILES_CMD` (required in production; command template with `{input_gltf}` and `{output_dir}`)

## Drone image sync contract

Photogrammetry flight will trigger camera capture and then wait for local images, but it does not
include a built-in radio/file-transfer stack. You must run a companion sync process that copies files:

- Direct mode: write images into `PHOTOGRAMMETRY_DRONE_SYNC_DIR/flight_<flight_id>`
- Staging mode: write images into `PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR` and backend imports them

Typical companion options:

- `rsync`/`scp` pull from drone SD card over Wi-Fi
- LTE uploader/downloader job that mirrors camera storage to ground station
- custom MAVFTP/media service bridge

Optional auto-trigger from backend:

- Set `PHOTOGRAMMETRY_CAPTURE_SYNC_CMD` to run your transfer tool when the mission finishes.
- Example:
  `PHOTOGRAMMETRY_CAPTURE_SYNC_CMD="rsync -a /mnt/drone_sd/DCIM/ {session_dir}/"`

If no sync agent is running, flight manifests will end with `status=completed_missing_images`.

## Run worker (prefork-compatible)

```bash
celery -A backend.tasks.celery_app:celery_app worker \
  --loglevel=INFO \
  --queues=photogrammetry \
  --hostname=photogrammetry@%h
```

This mode is safe with default Celery pools; tasks run on a reused background asyncio loop per worker process.

## Run native async worker (optional)

```bash
pip install celery-aio-pool
export CELERY_ENABLE_NATIVE_ASYNC_TASK=1
export CELERY_CUSTOM_WORKER_POOL='celery_aio_pool.pool:AsyncIOPool'
celery -A backend.tasks.celery_app:celery_app worker \
  --pool=custom \
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
