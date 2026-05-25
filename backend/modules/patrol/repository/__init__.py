from backend.modules.patrol.repository.alerts import PatrolAlertDecision, PatrolAlertMixin
from backend.modules.patrol.repository.detections import PatrolDetectionMixin
from backend.modules.patrol.repository.incidents import PatrolIncidentMixin
from backend.modules.patrol.repository.pipeline import PatrolPipelineMixin


class PatrolDetectionRepository(
    PatrolDetectionMixin, PatrolIncidentMixin, PatrolAlertMixin, PatrolPipelineMixin
):
    pass


__all__ = ["PatrolAlertDecision", "PatrolDetectionRepository"]
