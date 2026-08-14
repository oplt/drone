from __future__ import annotations

from backend.infrastructure.messaging.websocket_publisher.broadcast import BroadcastMixin
from backend.infrastructure.messaging.websocket_publisher.connection import ConnectionMixin
from backend.infrastructure.messaging.websocket_publisher.ingest import IngestMixin
from backend.infrastructure.messaging.websocket_publisher.lifecycle import LifecycleMixin
from backend.infrastructure.messaging.websocket_publisher.redis_fanout import RedisFanoutMixin
from backend.infrastructure.messaging.websocket_publisher.state import RuntimeStateMixin


class TelemetryWebSocketManager(
    RuntimeStateMixin,
    RedisFanoutMixin,
    IngestMixin,
    ConnectionMixin,
    LifecycleMixin,
    BroadcastMixin,
):
    """Manages WebSocket connections for real-time telemetry broadcasting.

    Concurrency invariants:
    - ``_lock`` (threading.Lock) protects ``_clients`` and ``active_connections``.
      It may be taken from async coroutines and from writer-task ``finally`` blocks;
      critical sections must stay short (map lookups / insert / delete only).
    - ``_running`` / ``_source_connected`` are updated from the sync MAVLink worker
      thread via ``set_runtime_active``; treat them as best-effort runtime flags.
    - Fan-out filtering uses per-client ``org_id`` and optional ``mission_runtime_id``
      subscription set via the telemetry WebSocket ``subscribe`` control message.
    """


telemetry_manager = TelemetryWebSocketManager()
