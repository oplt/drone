from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import (
    OrgUser,
    require_org_user,
    require_user,
)
from backend.modules.vision_models.api_dependencies import application, http_error
from backend.modules.vision_models.application import (
    VisionConflict,
    VisionNotFound,
    VisionValidationError,
)
from backend.modules.vision_models.schemas import (
    AnnotationImportOut,
    AnnotationReplace,
    DatasetImageOut,
    DatasetImagePage,
    ExtractFramesOut,
    ExtractFramesRequest,
    ImageSelectionPatch,
    ImageUploadResult,
)
from backend.observability.instruments import observed_span

router = APIRouter()


@router.post("/datasets/{dataset_id}/images", response_model=ImageUploadResult)
async def upload_images(
    dataset_id: str,
    files: list[UploadFile] = File(...),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> ImageUploadResult:
    try:
        return await application.upload_images(db, dataset_id, files, org_user.user)
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.post("/datasets/{dataset_id}/extract-frames", response_model=ExtractFramesOut)
async def extract_frames(
    dataset_id: str,
    payload: ExtractFramesRequest,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> ExtractFramesOut:
    try:
        with observed_span(
            "vision.dataset.extract_frames",
            video_id=payload.video_id,
            dataset_id=dataset_id,
        ):
            return await application.extract_frames(db, dataset_id, payload, org_user.user)
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.get("/datasets/{dataset_id}/images", response_model=DatasetImagePage)
async def list_images(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=60, ge=1, le=200),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> DatasetImagePage:
    try:
        items, total = await application.list_images(
            db, dataset_id, org_user.user, offset=offset, limit=limit
        )
    except VisionNotFound as exc:
        raise http_error(exc) from exc
    return DatasetImagePage(items=items, total=total, offset=offset, limit=limit)


@router.get("/images/{image_id}/content")
async def image_content(
    image_id: str,
    db=Depends(get_db),
    user=Depends(require_user),
) -> FileResponse:
    try:
        path = await application.resolve_image_media(db, image_id, user, thumbnail=False)
    except VisionNotFound as exc:
        raise http_error(exc) from exc
    return FileResponse(path, media_type="image/jpeg")


@router.get("/images/{image_id}/thumbnail")
async def image_thumbnail(
    image_id: str,
    db=Depends(get_db),
    user=Depends(require_user),
) -> FileResponse:
    try:
        path = await application.resolve_image_media(db, image_id, user, thumbnail=True)
    except VisionNotFound as exc:
        raise http_error(exc) from exc
    return FileResponse(path, media_type="image/jpeg")


@router.put("/images/{image_id}/annotations", response_model=DatasetImageOut)
async def replace_annotations(
    image_id: str,
    payload: AnnotationReplace,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> DatasetImageOut:
    try:
        return await application.replace_annotations(db, image_id, payload, org_user.user)
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.patch("/images/{image_id}", response_model=DatasetImageOut)
async def set_image_selection(
    image_id: str,
    payload: ImageSelectionPatch,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> DatasetImageOut:
    try:
        return await application.set_image_selected(db, image_id, payload.selected, org_user.user)
    except (VisionConflict, VisionNotFound) as exc:
        raise http_error(exc) from exc


@router.post(
    "/datasets/{dataset_id}/annotations/import/yolo",
    response_model=AnnotationImportOut,
)
async def import_yolo_annotations(
    dataset_id: str,
    file: UploadFile = File(...),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> AnnotationImportOut:
    content = await file.read(20 * 1024 * 1024 + 1)
    await file.close()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Annotation archive exceeds 20 MB")
    try:
        return await application.import_yolo_annotations(db, dataset_id, content, org_user.user)
    except (VisionConflict, VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc


@router.get("/datasets/{dataset_id}/export/yolo")
async def export_yolo_dataset(
    dataset_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> FileResponse:
    try:
        path, filename = await application.export_yolo_dataset(db, dataset_id, org_user.user)
    except (VisionNotFound, VisionValidationError) as exc:
        raise http_error(exc) from exc
    return FileResponse(path, media_type="application/zip", filename=filename)
