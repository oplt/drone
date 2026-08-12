from fastapi import HTTPException

from backend.modules.vision_models.application import (
    VisionApplication,
    VisionConflict,
    VisionNotFound,
    VisionWorkerUnavailable,
)

application = VisionApplication()


def http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VisionNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, VisionConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, VisionWorkerUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))
