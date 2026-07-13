# Backend architecture boundaries

The backend is a modular monolith with explicit process boundaries:

`router -> application service -> repository/domain -> infrastructure adapter`

Routers own authentication, parsing, and HTTP error mapping. They receive the
request-scoped `get_db` session and never create a second session. Repositories
own SQLAlchemy statements and projections. Queue, storage, AI, HTTP, ROS, and
vehicle integrations are ports with infrastructure implementations. Worker
entrypoints only wire Celery tasks to application services.

## Worker topology

Each queue has an intentional consumer and bounded concurrency:

| Queue | Consumer | Work | Policy |
| --- | --- | --- | --- |
| `default` | `worker` | short application jobs and agents | normal |
| `photogrammetry` | `worker-photogrammetry` | image/mapping CPU work | concurrency 1 |
| `exports` | `worker-exports` | filesystem/export jobs | concurrency 2 |
| `webhooks` | `worker-webhooks` | external delivery/retry | concurrency 4 |
| `notifications` | `worker-notifications` | outbox relay | concurrency 2 |
| `scheduling` | `worker-scheduling` | scheduled mission dispatch | concurrency 2 |
| `video-analysis` | `worker-video` | video decode/inference | concurrency 1 |
| `warehouse-mapping` | `worker-warehouse` | ROS/structure extraction | concurrency 1 |

Celery task time limits and retry policies remain task-owned. Worker health
checks use Celery ping; durable job status remains PostgreSQL/Redis-backed.

## API singleton ownership

Alert evaluation is protected by a Redis lease per cycle. The MQTT event
trigger subscriber owns `leader:patrol:event-trigger-mqtt` with a renewable
30-second lease, so only one API replica consumes the subscription. Lease loss
closes the subscriber; expiry permits another replica to take over.

The API lifespan owns only resource startup/shutdown and these leased adapters;
it does not treat process-local state as authoritative.

## Configuration and secrets

Compose uses one non-secret backend environment anchor. Service-specific
overrides stay local to each service. Secret values load from the optional
`BACKEND_ENV_FILE` (default `backend/.env`) or deployment secret injection;
production startup validation rejects known development credentials.
