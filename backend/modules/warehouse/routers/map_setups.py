from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.models import (
    WarehouseCoordinateFrame,
    WarehouseInspectionMission,
    WarehouseLayoutVersion,
    WarehouseMap,
    WarehouseMapSetupVersion,
    WarehouseModel,
    WarehouseScanTarget,
)
from backend.modules.warehouse.repository.maps import (
    WarehouseRepositoryError,
    _normalize_polygon_local,
    _polygon_area_m2,
)
from backend.modules.warehouse.service.coordinate_frames import validate_transform
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit
from backend.modules.warehouse.service.drift_guard import (
    ensure_no_active_missions_for_frame_change,
    transform_checksum,
    validate_localization_evidence,
    validate_scale_calibration,
)

router = APIRouter(tags=["warehouse-map-setups"])


class MapSetupCreate(BaseModel):
    polygon_local_m: list[list[float]] = Field(..., min_length=3)
    origin_transform: dict
    alignment_deg: float = Field(default=0.0, ge=-180.0, le=180.0)
    alignment_reference: Literal["north", "aisle"] = "aisle"
    source: str = Field(default="operator", min_length=1, max_length=64)
    confidence: float = Field(default=1.0, gt=0.0, le=1.0)
    transform_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    max_transform_age_s: float = Field(default=300.0, gt=0.0, le=86_400.0)
    covariance: list[float] = Field(default_factory=list, max_length=36)
    localization_method: str = Field(default="operator", min_length=1, max_length=64)
    map_resolution_m: float | None = Field(default=None, gt=0.0)
    scale: float = Field(default=1.0, ge=1.0, le=1.0)
    known_distance_expected_m: float | None = Field(default=None, gt=0.0)
    known_distance_measured_m: float | None = Field(default=None, gt=0.0)

    @field_validator("origin_transform")
    @classmethod
    def valid_origin(cls, value: dict) -> dict:
        return validate_transform(value)

    @field_validator("polygon_local_m")
    @classmethod
    def valid_polygon(cls, value: list[list[float]]) -> list[list[float]]:
        try:
            normalized = _normalize_polygon_local(value)
            _polygon_area_m2(normalized)
        except WarehouseRepositoryError as exc:
            raise ValueError(str(exc)) from exc
        return [list(point) for point in normalized]

    @field_validator("covariance")
    @classmethod
    def valid_covariance(cls, value: list[float]) -> list[float]:
        if value and len(value) != 36:
            raise ValueError("covariance must be empty or a row-major 6x6 matrix")
        return value

    @model_validator(mode="after")
    def valid_scale_evidence(self) -> MapSetupCreate:
        validate_scale_calibration(
            scale=self.scale,
            map_resolution_m=self.map_resolution_m,
            expected_distance_m=self.known_distance_expected_m,
            measured_distance_m=self.known_distance_measured_m,
        )
        return self


class MapSetupOut(BaseModel):
    id: int
    warehouse_map_id: int
    coordinate_frame_id: int | None
    version: int
    status: str
    polygon_local_m: list[list[float]]
    origin_transform: dict
    alignment_deg: float
    alignment_reference: str
    source: str
    confidence: float
    map_resolution_m: float | None
    scale: float
    scale_calibration: dict
    transform_timestamp: datetime
    max_transform_age_s: float
    covariance: list[float]
    localization_method: str
    created_at: datetime
    locked_at: datetime | None


def _out(row: WarehouseMapSetupVersion) -> MapSetupOut:
    return MapSetupOut(
        id=row.id,
        warehouse_map_id=row.warehouse_map_id,
        coordinate_frame_id=row.coordinate_frame_id,
        version=row.version,
        status=row.status,
        polygon_local_m=row.polygon_local_json,
        origin_transform=row.origin_transform_json,
        alignment_deg=row.alignment_deg,
        alignment_reference=row.alignment_reference,
        source=row.source,
        confidence=row.confidence,
        map_resolution_m=row.map_resolution_m,
        scale=row.scale,
        scale_calibration=dict(row.scale_calibration_json or {}),
        transform_timestamp=row.transform_timestamp,
        max_transform_age_s=row.max_transform_age_s,
        covariance=list(row.covariance_json or []),
        localization_method=row.localization_method,
        created_at=row.created_at,
        locked_at=row.locked_at,
    )


@router.get("/maps/{warehouse_map_id}/setups", response_model=list[MapSetupOut])
async def list_map_setups(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = (
        (
            await db.execute(
                select(WarehouseMapSetupVersion)
                .where(WarehouseMapSetupVersion.warehouse_map_id == warehouse_map_id)
                .order_by(WarehouseMapSetupVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_out(row) for row in rows]


@router.post(
    "/maps/{warehouse_map_id}/setups",
    response_model=MapSetupOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_map_setup(
    warehouse_map_id: int,
    payload: MapSetupCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    await db.execute(
        select(WarehouseMap.id).where(WarehouseMap.id == warehouse_map_id).with_for_update()
    )
    version = (
        int(
            (
                await db.execute(
                    select(func.coalesce(func.max(WarehouseMapSetupVersion.version), 0)).where(
                        WarehouseMapSetupVersion.warehouse_map_id == warehouse_map_id
                    )
                )
            ).scalar_one()
        )
        + 1
    )
    row = WarehouseMapSetupVersion(
        warehouse_map_id=warehouse_map_id,
        version=version,
        status="draft",
        polygon_local_json=payload.polygon_local_m,
        origin_transform_json=payload.origin_transform,
        alignment_deg=payload.alignment_deg,
        alignment_reference=payload.alignment_reference,
        source=payload.source.strip(),
        confidence=payload.confidence,
        map_resolution_m=payload.map_resolution_m,
        scale=payload.scale,
        scale_calibration_json=validate_scale_calibration(
            scale=payload.scale,
            map_resolution_m=payload.map_resolution_m,
            expected_distance_m=payload.known_distance_expected_m,
            measured_distance_m=payload.known_distance_measured_m,
        ),
        transform_timestamp=payload.transform_timestamp,
        max_transform_age_s=payload.max_transform_age_s,
        covariance_json=payload.covariance,
        localization_method=payload.localization_method.strip(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    emit_coordinate_audit(
        event_name="warehouse_map_setup_draft_created",
        action="edit_origin_boundary",
        resource_type="warehouse_map_setup",
        resource_id=row.id,
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason=row.source,
        old_value=None,
        new_value={
            "polygon_local_m": row.polygon_local_json,
            "origin_transform": row.origin_transform_json,
            "alignment_deg": row.alignment_deg,
            "alignment_reference": row.alignment_reference,
        },
        validation_result="pass",
        extra={"setup_version": row.version, "confidence": row.confidence},
    )
    return _out(row)


@router.get("/maps/{warehouse_map_id}/setups/{setup_id}/preview")
async def preview_map_setup(
    warehouse_map_id: int,
    setup_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    setup = await db.get(WarehouseMapSetupVersion, setup_id)
    if setup is None or setup.warehouse_map_id != warehouse_map_id:
        raise HTTPException(404, "Warehouse map setup not found")
    models, layouts, targets, missions = [
        int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(model)
                    .where(model.warehouse_map_id == warehouse_map_id)
                )
            ).scalar_one()
        )
        for model in (
            WarehouseModel,
            WarehouseLayoutVersion,
            WarehouseScanTarget,
            WarehouseInspectionMission,
        )
    ]
    active = (
        await db.execute(
            select(WarehouseCoordinateFrame).where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
        )
    ).scalar_one_or_none()
    return {
        "setup_id": setup.id,
        "from_coordinate_frame_id": active.id if active else None,
        "origin_before": active.transform_json if active else None,
        "origin_after": setup.origin_transform_json,
        "affected": {
            "models": models,
            "layouts": layouts,
            "targets": targets,
            "missions": missions,
        },
        "policy": "Existing children remain pinned; regenerate or explicitly migrate them.",
    }


@router.post("/maps/{warehouse_map_id}/setups/{setup_id}/lock", response_model=MapSetupOut)
async def lock_map_setup(
    warehouse_map_id: int,
    setup_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    warehouse_map = await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    await db.execute(
        select(WarehouseMap.id).where(WarehouseMap.id == warehouse_map_id).with_for_update()
    )
    setup = await db.get(WarehouseMapSetupVersion, setup_id)
    if setup is None or setup.warehouse_map_id != warehouse_map_id:
        raise HTTPException(404, "Warehouse map setup not found")
    if setup.status != "draft":
        raise HTTPException(409, "Only draft map setups can be locked")
    await ensure_no_active_missions_for_frame_change(db, warehouse_map_id=warehouse_map_id)
    try:
        validate_localization_evidence(
            transform=setup.origin_transform_json,
            transform_timestamp=setup.transform_timestamp,
            max_age_s=setup.max_transform_age_s,
            covariance=list(setup.covariance_json or []),
            confidence=float(setup.confidence),
        )
    except ValueError as exc:
        raise HTTPException(409, f"Map setup localization evidence is unsafe: {exc}") from exc
    previous_frame = (
        await db.execute(
            select(WarehouseCoordinateFrame).where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    frame_version = (
        int(
            (
                await db.execute(
                    select(func.coalesce(func.max(WarehouseCoordinateFrame.version), 0)).where(
                        WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id
                    )
                )
            ).scalar_one()
        )
        + 1
    )
    await db.execute(
        update(WarehouseCoordinateFrame)
        .where(
            WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
            WarehouseCoordinateFrame.status == "locked",
        )
        .values(status="superseded", superseded_at=now)
    )
    await db.execute(
        update(WarehouseMapSetupVersion)
        .where(
            WarehouseMapSetupVersion.warehouse_map_id == warehouse_map_id,
            WarehouseMapSetupVersion.status == "locked",
        )
        .values(status="superseded", superseded_at=now)
    )
    frame = WarehouseCoordinateFrame(
        warehouse_map_id=warehouse_map_id,
        version=frame_version,
        parent_frame_id="warehouse_map",
        child_frame_id="odom",
        units="m",
        axis_convention="ENU",
        handedness="right",
        transform_json=setup.origin_transform_json,
        covariance_json=list(setup.covariance_json or []),
        source=f"map_setup:{setup.id}",
        localization_method=setup.localization_method,
        transform_timestamp=setup.transform_timestamp,
        max_age_s=setup.max_transform_age_s,
        transform_checksum=transform_checksum(setup.origin_transform_json),
        confidence=setup.confidence,
        status="locked",
        locked_at=now,
    )
    db.add(frame)
    await db.flush()
    setup.status, setup.locked_at, setup.coordinate_frame_id = "locked", now, frame.id
    meta = dict(warehouse_map.meta_data or {})
    meta.update(
        {
            "polygon_local_m": setup.polygon_local_json,
            "setup_status": "locked",
            "setup_version": setup.version,
            "origin_transform": setup.origin_transform_json,
            "alignment_deg": setup.alignment_deg,
            "alignment_reference": setup.alignment_reference,
        }
    )
    warehouse_map.meta_data = meta
    warehouse_map.area_m2 = _polygon_area_m2(setup.polygon_local_json)
    await db.commit()
    await db.refresh(setup)
    emit_coordinate_audit(
        event_name="warehouse_map_setup_locked",
        action="lock_origin_boundary",
        resource_type="warehouse_map_setup",
        resource_id=setup.id,
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason=setup.source,
        coordinate_frame_id=frame.id,
        coordinate_frame_version=frame.version,
        old_value={
            "coordinate_frame_id": previous_frame.id if previous_frame else None,
            "origin_transform": previous_frame.transform_json if previous_frame else None,
        },
        new_value={
            "polygon_local_m": setup.polygon_local_json,
            "origin_transform": setup.origin_transform_json,
            "alignment_deg": setup.alignment_deg,
            "alignment_reference": setup.alignment_reference,
        },
        covariance=list(frame.covariance_json or []),
        validation_result="pass",
        extra={"setup_version": setup.version, "confidence": setup.confidence},
    )
    return _out(setup)
