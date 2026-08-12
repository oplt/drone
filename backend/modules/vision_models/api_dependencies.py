from backend.core.api_errors import DomainApiError, map_domain_exception
from backend.modules.vision_models.application import (
    VisionApplication,
)

application = VisionApplication()


def http_error(exc: Exception) -> DomainApiError:
    error = map_domain_exception(exc, domain="vision")
    if type(exc).__name__ == "VisionAnnotationConflict":
        error.code = "VISION_ANNOTATION_REVISION_CONFLICT"
    return error
