"""Prometheus metric definitions for the drone platform."""
from prometheus_client import Counter, Gauge, Histogram  # noqa: F401

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
