import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import (
    OrgUser,
    require_org_user,
    require_user_header_or_query,
)
from backend.modules.vision_models.api_dependencies import application, http_error
from backend.modules.vision_models.application import (
    VisionConflict,
    VisionNotFound,
    VisionValidationError,
    VisionWorkerUnavailable,
)
from backend.modules.vision_models.schemas import (
    ModelEvaluationOut,
    ModelVersionOut,
    ReleaseActionRequest,
    TrainingRunCreate,
    TrainingRunOut,
)

router = APIRouter()


def artifact_media_type(path: Path) -> str:
    with path.open("rb") as source:
        signature = source.read(16)
    if signature.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


@router.post(
    "/projects/{project_id}/training-runs",
    response_model=TrainingRunOut,
    status_code=202,
)
async def create_training_run(
    project_id: str,
    payload: TrainingRunCreate,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> TrainingRunOut:
    try:
        return await application.create_training_run(db, project_id, payload, org_user.user)
    except (
        VisionConflict,
        VisionNotFound,
        VisionValidationError,
        VisionWorkerUnavailable,
    ) as exc:
        raise http_error(exc) from exc


@router.get("/projects/{project_id}/training-runs", response_model=list[TrainingRunOut])
async def list_training_runs(
    project_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[TrainingRunOut]:
    try:
        return await application.list_training_runs(db, project_id, org_user.user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc


@router.get("/training-runs/{run_id}", response_model=TrainingRunOut)
async def get_training_run(
    run_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> TrainingRunOut:
    try:
        return await application.get_training_run(db, run_id, org_user.user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc


@router.post("/training-runs/{run_id}/cancel", response_model=TrainingRunOut)
async def cancel_training_run(
    run_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> TrainingRunOut:
    try:
        return await application.cancel_training_run(db, run_id, org_user.user)
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.get("/models", response_model=list[ModelVersionOut])
async def list_models(
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[ModelVersionOut]:
    return await application.list_models(db, org_user.user)


@router.get("/models/{model_id}/versions", response_model=list[ModelVersionOut])
async def list_model_versions(
    model_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[ModelVersionOut]:
    try:
        return await application.list_model_versions(db, model_id, org_user.user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc


@router.post("/model-versions/{version_id}/deploy", response_model=ModelVersionOut)
async def deploy_model(
    version_id: str,
    payload: ReleaseActionRequest | None = None,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> ModelVersionOut:
    try:
        return await application.deploy_model(
            db,
            version_id,
            org_user.user,
            override=payload.override if payload else False,
            reason=payload.reason if payload else None,
        )
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.post("/model-versions/{version_id}/archive", response_model=ModelVersionOut)
async def archive_model(
    version_id: str,
    payload: ReleaseActionRequest | None = None,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> ModelVersionOut:
    try:
        return await application.archive_model(
            db,
            version_id,
            org_user.user,
            override=payload.override if payload else False,
            reason=payload.reason if payload else None,
        )
    except (VisionConflict, VisionNotFound) as exc:
        raise http_error(exc) from exc


@router.post("/model-versions/{version_id}/rollback", response_model=ModelVersionOut)
async def rollback_model(
    version_id: str,
    payload: ReleaseActionRequest | None = None,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> ModelVersionOut:
    try:
        return await application.rollback_model(
            db,
            version_id,
            org_user.user,
            reason=payload.reason if payload else None,
        )
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.get("/model-versions/{version_id}/evaluation", response_model=ModelEvaluationOut)
async def get_evaluation(
    version_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> ModelEvaluationOut:
    try:
        return await application.get_evaluation(db, version_id, org_user.user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc


@router.get("/model-versions/{version_id}/evaluation-artifacts/{name}")
async def get_evaluation_artifact(
    version_id: str,
    name: str,
    db=Depends(get_db),
    user=Depends(require_user_header_or_query),
) -> FileResponse:
    try:
        path = await application.resolve_evaluation_artifact(db, version_id, name, user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc
    return FileResponse(
        path,
        media_type=artifact_media_type(path),
        filename=path.name,
        content_disposition_type="inline",
    )
