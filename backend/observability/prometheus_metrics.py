"""Prometheus metric definitions for the drone platform."""

from prometheus_client import Counter, Gauge, Histogram

# --- HTTP API ---

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being processed",
    ["method", "route"],
)

http_exceptions_total = Counter(
    "http_exceptions_total",
    "Total unhandled HTTP exceptions",
    ["method", "route", "exception_type"],
)

# --- Jobs / workers ---

jobs_started_total = Counter(
    "jobs_started_total",
    "Total background jobs started",
    ["job_name", "queue"],
)

jobs_completed_total = Counter(
    "jobs_completed_total",
    "Total background jobs completed successfully",
    ["job_name", "queue"],
)

jobs_failed_total = Counter(
    "jobs_failed_total",
    "Total background jobs failed",
    ["job_name", "queue", "error_type"],
)

job_duration_seconds = Histogram(
    "job_duration_seconds",
    "Background job execution duration in seconds",
    ["job_name", "queue"],
    buckets=(0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0),
)

job_retries_total = Counter(
    "job_retries_total",
    "Total background job retry attempts",
    ["job_name", "queue", "retry_reason"],
)

job_dead_letter_total = Counter(
    "job_dead_letter_total",
    "Total jobs moved to dead-letter after max retries",
    ["job_name", "queue"],
)

queue_lag_seconds = Histogram(
    "queue_lag_seconds",
    "Time between job enqueue and worker start in seconds",
    ["queue"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

queue_depth = Gauge(
    "queue_depth",
    "Number of pending messages in a queue",
    ["queue"],
)

# --- Database ---

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

db_errors_total = Counter(
    "db_errors_total",
    "Total database errors",
    ["operation", "error_type"],
)

db_connection_errors_total = Counter(
    "db_connection_errors_total",
    "Total database connection errors",
)

db_pool_active_connections = Gauge(
    "db_pool_active_connections",
    "Active database pool connections",
)

db_pool_idle_connections = Gauge(
    "db_pool_idle_connections",
    "Idle database pool connections",
)

# --- External APIs ---

external_api_requests_total = Counter(
    "external_api_requests_total",
    "Total outbound external API requests",
    ["service", "endpoint_group", "status_code"],
)

external_api_request_duration_seconds = Histogram(
    "external_api_request_duration_seconds",
    "Outbound external API request duration in seconds",
    ["service", "endpoint_group"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

external_api_errors_total = Counter(
    "external_api_errors_total",
    "Total outbound external API errors",
    ["service", "error_type"],
)

# --- Reliability / scheduler ---

retry_count_total = Counter(
    "retry_count_total",
    "Total retry attempts across subsystems",
    ["subsystem", "reason"],
)

stale_data_detected_total = Counter(
    "stale_data_detected_total",
    "Total stale-data detections",
    ["source"],
)

fallback_used_total = Counter(
    "fallback_used_total",
    "Total safe fallback usages",
    ["subsystem", "fallback_type"],
)

scheduler_runs_total = Counter(
    "scheduler_runs_total",
    "Total scheduler/beat task runs",
    ["scheduler_name"],
)

scheduler_failures_total = Counter(
    "scheduler_failures_total",
    "Total scheduler/beat task failures",
    ["scheduler_name", "error_type"],
)

scheduler_lag_seconds = Gauge(
    "scheduler_lag_seconds",
    "Scheduler lag in seconds since last successful run",
    ["scheduler_name"],
)

# --- Domain-specific (retained for backward compatibility) ---

active_drone_connections = Gauge(
    "drone_active_connections",
    "Number of active drone connections",
)

mission_command_count = Counter(
    "drone_mission_commands_total",
    "Total mission commands issued",
    ["command_type"],
)

failed_mission_command_count = Counter(
    "drone_mission_command_failures_total",
    "Total failed mission commands",
    ["command_type"],
)

telemetry_messages_received = Counter(
    "drone_telemetry_messages_received_total",
    "Total telemetry messages received",
    ["source"],
)

telemetry_lag_seconds = Gauge(
    "drone_telemetry_lag_seconds",
    "Latest telemetry lag/freshness in seconds",
    ["source"],
)

video_analysis_jobs_total = Counter(
    "drone_video_analysis_jobs_total",
    "Total video analysis jobs",
    ["status"],
)

video_analysis_job_failures = Counter(
    "drone_video_analysis_job_failures_total",
    "Total failed video analysis jobs",
    ["reason"],
)

celery_task_duration_seconds = Histogram(
    "drone_celery_task_duration_seconds",
    "Celery task duration in seconds (legacy alias)",
    ["task_name", "status"],
)

redis_queue_depth = Gauge(
    "drone_redis_queue_depth",
    "Redis queue depth (legacy alias)",
    ["queue_name"],
)

telemetry_envelopes_total = Counter(
    "telemetry_envelopes_total",
    "Total telemetry envelopes processed by the orchestrator",
)

websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Number of currently active WebSocket connections",
)

orchestrator_queue_depth = Gauge(
    "orchestrator_queue_depth",
    "Current depth of orchestrator internal queues",
    ["queue_name"],
)

mission_starts_total = Counter(
    "mission_starts_total",
    "Total missions started",
    ["mission_type"],
)

mission_ends_total = Counter(
    "mission_ends_total",
    "Total missions ended",
    ["mission_type", "terminal_state"],
)

preflight_runs_total = Counter(
    "preflight_runs_total",
    "Total preflight runs executed",
    ["overall_status"],
)

warehouse_preflight_refresh_total = Counter(
    "warehouse_preflight_refresh_total",
    "Total warehouse preflight refresh attempts",
    ["status", "deep", "force"],
)

warehouse_preflight_refresh_duration_seconds = Histogram(
    "warehouse_preflight_refresh_duration_seconds",
    "Warehouse preflight refresh duration in seconds",
    ["deep", "force"],
)

warehouse_mapping_replay_duration_seconds = Histogram(
    "warehouse_mapping_replay_duration_seconds",
    "Warehouse live-map snapshot replay duration in seconds",
)

warehouse_preflight_cache_serves_total = Counter(
    "warehouse_preflight_cache_serves_total",
    "Total warehouse preflight snapshots served from cache",
    ["state"],
)

patrol_missions_started_total = Counter(
    "patrol_missions_started_total",
    "Total Property Patrol Mission runs started",
)

patrol_missions_completed_total = Counter(
    "patrol_missions_completed_total",
    "Total Property Patrol Mission runs completed",
)

patrol_missions_failed_total = Counter(
    "patrol_missions_failed_total",
    "Total Property Patrol Mission runs failed",
)

patrol_sensor_events_received_total = Counter(
    "patrol_sensor_events_received_total",
    "Total Property Patrol sensor events received",
)

patrol_sensor_events_rejected_total = Counter(
    "patrol_sensor_events_rejected_total",
    "Total Property Patrol sensor events rejected",
)

patrol_incidents_created_total = Counter(
    "patrol_incidents_created_total",
    "Total Property Patrol incidents created",
)

patrol_dispatch_latency_seconds = Histogram(
    "patrol_dispatch_latency_seconds",
    "Property Patrol dispatch latency in seconds",
)

patrol_preflight_failures_total = Counter(
    "patrol_preflight_failures_total",
    "Total Property Patrol preflight failures",
)

# --- Warehouse coordinate / localization ---

warehouse_tf_lookup_failures_total = Counter(
    "warehouse_tf_lookup_failures_total",
    "Total warehouse live-map TF lookup failures at message timestamp",
    ["source"],
)

warehouse_frame_mismatch_total = Counter(
    "warehouse_frame_mismatch_total",
    "Total warehouse live-map frame mismatches",
    ["layer"],
)

warehouse_inspection_validation_duration_seconds = Histogram(
    "warehouse_inspection_validation_duration_seconds",
    "Warehouse inspection path validation duration in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

warehouse_mission_rejection_total = Counter(
    "warehouse_mission_rejection_total",
    "Total warehouse mission plan/execute rejections",
    ["reason"],
)

warehouse_slam_localization_stale_total = Counter(
    "warehouse_slam_localization_stale_total",
    "Total SLAM localization staleness events during warehouse missions",
)

warehouse_transform_jump_total = Counter(
    "warehouse_transform_jump_total",
    "Total warehouse map-to-odom transform jump detections",
    ["source"],
)

KNOWN_QUEUES = (
    "default",
    "photogrammetry",
    "video-analysis",
    "warehouse-mapping",
    "exports",
    "webhooks",
    "scheduling",
    "notifications",
)
