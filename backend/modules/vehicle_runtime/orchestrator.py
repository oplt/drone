from __future__ import annotations

from .completion_service import RuntimeCompletionServiceMixin
from .coordination import RuntimeCoordinationMixin
from .event_service import RuntimeEventServiceMixin
from .execution_service import RuntimeExecutionServiceMixin
from .persistence_service import RuntimePersistenceMixin
from .recovery_service import RuntimeRecoveryServiceMixin
from .telemetry_service import RuntimeTelemetryServiceMixin
from .video_service import RuntimeVideoServiceMixin


class Orchestrator(
    RuntimeCoordinationMixin,
    RuntimePersistenceMixin,
    RuntimeEventServiceMixin,
    RuntimeTelemetryServiceMixin,
    RuntimeVideoServiceMixin,
    RuntimeRecoveryServiceMixin,
    RuntimeCompletionServiceMixin,
    RuntimeExecutionServiceMixin,
):
    """Stable vehicle runtime facade composed from focused application services."""
