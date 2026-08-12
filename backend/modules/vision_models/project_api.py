from fastapi import APIRouter, Depends, Response

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.vision_models.api_dependencies import application, http_error
from backend.modules.vision_models.application import (
    VisionConflict,
    VisionNotFound,
    VisionValidationError,
)
from backend.modules.vision_models.schemas import (
    DatasetCreate,
    DatasetOut,
    VisionProjectCreate,
    VisionProjectOut,
    VisionProjectPatch,
)

router = APIRouter()


@router.post("/projects", response_model=VisionProjectOut, status_code=201)
async def create_project(
    payload: VisionProjectCreate,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VisionProjectOut:
    try:
        return await application.create_project(db, payload, org_user.user)
    except (VisionConflict, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.get("/projects", response_model=list[VisionProjectOut])
async def list_projects(
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[VisionProjectOut]:
    return await application.list_projects(db, org_user.user)


@router.get("/projects/{project_id}", response_model=VisionProjectOut)
async def get_project(
    project_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VisionProjectOut:
    try:
        return await application.get_project(db, project_id, org_user.user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc


@router.patch("/projects/{project_id}", response_model=VisionProjectOut)
async def patch_project(
    project_id: str,
    payload: VisionProjectPatch,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VisionProjectOut:
    try:
        return await application.patch_project(db, project_id, payload, org_user.user)
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> Response:
    try:
        await application.delete_project(db, project_id, org_user.user)
    except (VisionConflict, VisionNotFound) as exc:
        raise http_error(exc) from exc
    return Response(status_code=204)


@router.post("/projects/{project_id}/datasets", response_model=DatasetOut, status_code=201)
async def create_dataset(
    project_id: str,
    payload: DatasetCreate | None = None,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> DatasetOut:
    try:
        return await application.create_dataset(
            db,
            project_id,
            org_user.user,
            clone_from_dataset_id=(payload.clone_from_dataset_id if payload else None),
        )
    except (VisionConflict, VisionNotFound) as exc:
        raise http_error(exc) from exc


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetOut])
async def list_datasets(
    project_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[DatasetOut]:
    try:
        return await application.list_datasets(db, project_id, org_user.user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> DatasetOut:
    try:
        return await application.get_dataset(db, dataset_id, org_user.user)
    except VisionNotFound as exc:
        raise http_error(exc) from exc
