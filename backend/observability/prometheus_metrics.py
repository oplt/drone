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

celery_soft_time_limit_total = Counter(
    "celery_soft_time_limit_total",
    "Celery tasks that hit the soft time limit",
    ["job_name", "queue"],
)

blocking_boundary_duration_seconds = Histogram(
    "blocking_boundary_duration_seconds",
    "Duration of process, filesystem, and CPU adapter calls",
    ["boundary", "operation"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 120.0, 600.0),
)

blocking_boundary_failures_total = Counter(
    "blocking_boundary_failures_total",
    "Failures in blocking adapter calls",
    ["boundary", "operation"],
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

cache_hits_total = Counter(
    "cache_hits_total",
    "Read-through cache hits",
    ["cache"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Read-through cache misses",
    ["cache"],
)

analytics_overview_cache_latency_seconds = Histogram(
    "analytics_overview_cache_latency_seconds",
    "Analytics overview cache operation latency",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)


celery_workers_ready = Gauge(
    "celery_workers_ready",
    "Number of Celery workers responding to readiness probes",
    ["queue"],
)

ai_requests_total = Counter(
    "ai_requests_total",
    "AI gateway requests by task, provider, and outcome",
    ["task", "provider", "status"],
)

ai_request_duration_seconds = Histogram(
    "ai_request_duration_seconds",
    "AI gateway request latency",
    ["task"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

ai_fallback_total = Counter(
    "ai_fallback_total",
    "AI gateway fallback provider selections",
    ["task"],
)

ai_abstentions_total = Counter(
    "ai_abstentions_total",
    "AI outputs below confidence threshold or requiring abstention",
    ["task"],
)

ai_tokens_total = Counter(
    "ai_tokens_total",
    "AI provider-reported token usage by task/provider/kind",
    ["task", "provider", "kind"],
)

video_inference_queue_depth = Gauge(
    "video_inference_queue_depth",
    "Pending video detections waiting for persistence",
    ["job_id"],
)

video_yolo_cache_entries = Gauge(
    "video_yolo_cache_entries",
    "YOLO / SAHI model instances cached in the current worker process",
)

video_yolo_cache_evictions_total = Counter(
    "video_yolo_cache_evictions_total",
    "LRU evictions from the worker-local YOLO model cache",
)

agriculture_runs_started_total = Counter(
    "agriculture_runs_started_total", "Agriculture analysis runs started", ["queue"]
)
agriculture_runs_completed_total = Counter(
    "agriculture_runs_completed_total", "Agriculture analysis runs completed", ["queue", "status"]
)
agriculture_runs_failed_total = Counter(
    "agriculture_runs_failed_total", "Agriculture analysis run failures", ["queue", "error_type"]
)
agriculture_run_duration_seconds = Histogram(
    "agriculture_run_duration_seconds", "Agriculture analysis run duration", ["queue"]
)
agriculture_georeference_rate = Gauge(
    "agriculture_georeference_rate", "Latest agriculture run georeference success ratio", ["stage"]
)
agriculture_observations_total = Gauge(
    "agriculture_observations_total", "Latest agriculture observation count", ["stage"]
)
agriculture_inference_latency_seconds = Histogram(
    "agriculture_inference_latency_seconds", "Agriculture inference stage latency", ["stage"]
)
agriculture_queue_age_seconds = Histogram(
    "agriculture_queue_age_seconds", "Agriculture queue age at worker start", ["queue"]
)
agriculture_queue_depth = Gauge(
    "agriculture_queue_depth", "Observed pending agriculture jobs", ["queue"]
)
agriculture_dead_letters_total = Counter(
    "agriculture_dead_letters_total", "Agriculture jobs moved to dead letter", ["task"]
)
agriculture_stage_failures_total = Counter(
    "agriculture_stage_failures_total", "Failed agriculture pipeline stages", ["stage", "error_type"]
)
agriculture_telemetry_gaps_total = Counter(
    "agriculture_telemetry_gaps_total", "Detected agriculture telemetry gaps", ["source"]
)

agriculture_runtime_commands_total = Counter(
    "agriculture_runtime_commands_total",
    "Agriculture runtime commands accepted, rejected, or replayed",
    ["command", "outcome"],
)

agriculture_runtime_command_failures_total = Counter(
    "agriculture_runtime_command_failures_total",
    "Agriculture runtime command failures by reason",
    ["command", "reason"],
)
agriculture_frames_total = Counter(
    "agriculture_frames_total", "Agriculture frame outcomes", ["stage", "outcome"]
)
agriculture_quality_rejections_total = Counter(
    "agriculture_quality_rejections_total", "Agriculture frames rejected by quality gates", ["reason"]
)
agriculture_observation_area_m2 = Gauge(
    "agriculture_observation_area_m2", "Latest total agriculture observation area", ["stage"]
)
agriculture_dedup_ratio = Gauge(
    "agriculture_dedup_ratio", "Latest agriculture spatial temporal deduplication ratio", ["stage"]
)
agriculture_output_size_bytes = Histogram(
    "agriculture_output_size_bytes", "Agriculture stage output bytes", ["stage"]
)
agriculture_storage_bytes = Gauge(
    "agriculture_storage_bytes", "Agriculture object storage usage", ["tenant", "backend"]
)
agriculture_repeated_failures = Gauge(
    "agriculture_repeated_failures", "Current retry count for an agriculture run", ["run_id"]
)
agriculture_model_drift_score = Gauge(
    "agriculture_model_drift_score", "Latest agriculture model drift score", ["model", "slice"]
)
agriculture_worker_saturation = Gauge(
    "agriculture_worker_saturation", "Agriculture worker saturation ratio", ["queue", "resource"]
)
agriculture_live_processors = Gauge(
    "agriculture_live_processors",
    "Active agriculture live advisory processors in this API process",
)

event_loop_lag_seconds = Gauge(
    "event_loop_lag_seconds",
    "Observed asyncio event-loop scheduling lag",
)

profiling_stage_duration_seconds = Histogram(
    "profiling_stage_duration_seconds",
    "Measured duration of geometry, planning, and parsing stages",
    ["stage", "workload"],
    buckets=(0.001, 0.01, 0.1, 0.5, 1.0, 5.0, 15.0, 60.0, 300.0),
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

db_session_hold_duration_seconds = Histogram(
    "db_session_hold_duration_seconds",
    "Time an async DB session remained checked out for a scoped operation",
    ["scope"],
    buckets=(0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0),
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

websocket_auth_failures_total = Counter(
    "websocket_auth_failures_total",
    "Telemetry WebSocket authentication failures",
    ["reason"],
)

telemetry_redis_fallback_total = Counter(
    "telemetry_redis_fallback_total",
    "Telemetry fan-out degraded to in-process broadcast or subscriber reconnect",
    ["reason"],
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

warehouse_structure_extraction_failures_total = Counter(
    "warehouse_structure_extraction_failures_total",
    "Total warehouse structure extraction failures by reason",
    ["reason"],
)

warehouse_low_confidence_candidates_total = Counter(
    "warehouse_low_confidence_candidates_total",
    "Total warehouse layout/inspection candidates emitted below the confidence threshold",
    ["source"],
)

warehouse_layout_publish_blocks_total = Counter(
    "warehouse_layout_publish_blocks_total",
    "Total warehouse layout publish attempts blocked by validation gates",
    ["reason"],
)

warehouse_inspection_target_clearance_failures_total = Counter(
    "warehouse_inspection_target_clearance_failures_total",
    "Total warehouse inspection target clearance failures during extraction",
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
    "agriculture-ingest",
    "agriculture-quality",
    "agriculture-rgb-inference",
    "agriculture-segmentation",
    "agriculture-geospatial",
    "agriculture-temporal",
    "agriculture-fusion",
    "agriculture-exports",
    "agriculture-dead-letter",
)
