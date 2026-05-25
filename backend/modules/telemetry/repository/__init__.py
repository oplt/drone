from backend.core.database.session import Session
from backend.modules.telemetry.repository.batcher import TelemetryBatcher
from backend.modules.telemetry.repository.ingest import TelemetryIngestMixin
from backend.modules.telemetry.repository.lifecycle import TelemetryLifecycleMixin
from backend.modules.telemetry.repository.summaries import TelemetrySummaryMixin


class TelemetryRepository(TelemetryLifecycleMixin, TelemetryIngestMixin, TelemetrySummaryMixin):
    def __init__(self, session_factory: type[Session] = Session) -> None:
        self._session_factory = session_factory


__all__ = ["TelemetryBatcher", "TelemetryRepository"]
