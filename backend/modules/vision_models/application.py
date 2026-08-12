from backend.modules.vision_models.annotation_operations import AnnotationOperations
from backend.modules.vision_models.application_base import (
    VisionApplicationBase,
    VisionAnnotationConflict,
    VisionConflict,
    VisionNotFound,
    VisionValidationError,
    VisionWorkerUnavailable,
)
from backend.modules.vision_models.dataset_ingestion_operations import (
    DatasetIngestionOperations,
)
from backend.modules.vision_models.project_operations import ProjectOperations
from backend.modules.vision_models.training_operations import TrainingOperations


class VisionApplication(
    ProjectOperations,
    DatasetIngestionOperations,
    AnnotationOperations,
    TrainingOperations,
    VisionApplicationBase,
):
    """Tenant-scoped facade over the vision-model workflow operations."""


__all__ = [
    "VisionApplication",
    "VisionAnnotationConflict",
    "VisionConflict",
    "VisionNotFound",
    "VisionValidationError",
    "VisionWorkerUnavailable",
]
