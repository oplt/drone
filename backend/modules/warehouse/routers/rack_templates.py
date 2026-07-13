from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseRackTemplate,
    WarehouseRackTemplateVersion,
    WarehouseShelf,
)
from backend.modules.warehouse.service.layout import (
    bump_revision,
    parse_revision,
    require_draft_revision,
)
from backend.modules.warehouse.service.rack_templates import (
    apply_template_to_rack_geometry,
    template_summary,
)

router = APIRouter(tags=["warehouse-rack-templates"])


RackTemplatePage = Page[dict[str, Any]]


class RackTemplateSpecIn(BaseModel):
    bay_width_m: float = Field(..., gt=0.0, le=20.0)
    shelf_heights_m: list[float] = Field(..., min_length=1, max_length=12)
    bin_pitch_m: float = Field(..., gt=0.0, le=10.0)
    bin_count: int | None = Field(default=None, ge=1, le=80)
    left_face_naming: str = Field(default="left_to_right", max_length=32)
    right_face_naming: str = Field(default="right_to_left", max_length=32)
    barcode_scan_side: str = Field(default="front", max_length=32)
    preferred_standoff_m: float = Field(default=1.2, gt=0.0, le=20.0)
    min_scanner_angle_deg: float = Field(default=20.0, ge=0.0, le=90.0)
    meta_data: dict = Field(default_factory=dict)

    @field_validator("shelf_heights_m")
    @classmethod
    def _sorted_heights(cls, value: list[float]) -> list[float]:
        heights = sorted({round(float(item), 4) for item in value if float(item) >= 0.0})
        if not heights:
            raise ValueError("shelf_heights_m must contain at least one non-negative height")
        return heights[:12]


class RackTemplateCreateIn(RackTemplateSpecIn):
    name: str = Field(..., min_length=1, max_length=128)
    rack_type: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2048)


class RackTemplateVersionCreateIn(RackTemplateSpecIn):
    status: Literal["draft", "active"] = "active"


class RackTemplateAssignIn(BaseModel):
    template_version_id: int = Field(..., ge=1)
    revision: int | None = None


def _version_from_payload(
    *,
    template_id: int,
    version: int,
    payload: RackTemplateSpecIn,
    status: str = "active",
) -> WarehouseRackTemplateVersion:
    now = datetime.now(UTC)
    return WarehouseRackTemplateVersion(
        template_id=int(template_id),
        version=int(version),
        status=status,
        bay_width_m=float(payload.bay_width_m),
        shelf_heights_json=[float(value) for value in payload.shelf_heights_m],
        bin_pitch_m=float(payload.bin_pitch_m),
        bin_count=payload.bin_count,
        left_face_naming=payload.left_face_naming,
        right_face_naming=payload.right_face_naming,
        barcode_scan_side=payload.barcode_scan_side,
        preferred_standoff_m=float(payload.preferred_standoff_m),
        min_scanner_angle_deg=float(payload.min_scanner_angle_deg),
        meta_data=dict(payload.meta_data or {}),
        activated_at=now if status == "active" else None,
    )


def _template_out(
    template: WarehouseRackTemplate,
    version: WarehouseRackTemplateVersion | None,
) -> dict:
    payload = {
        "id": int(template.id),
        "warehouse_map_id": int(template.warehouse_map_id),
        "name": template.name,
        "rack_type": template.rack_type,
        "description": template.description,
        "active": bool(template.active),
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }
    if version is not None:
        payload["current_version"] = template_summary(template, version)
    return payload


@router.get(
    "/maps/{warehouse_map_id}/rack-templates",
    response_model=RackTemplatePage,
)
async def list_rack_templates(
    warehouse_map_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = (
        await db.execute(
            select(WarehouseRackTemplate, WarehouseRackTemplateVersion)
            .join(
                WarehouseRackTemplateVersion,
                WarehouseRackTemplateVersion.template_id == WarehouseRackTemplate.id,
                isouter=True,
            )
            .where(
                WarehouseRackTemplate.warehouse_map_id == int(warehouse_map_id),
                WarehouseRackTemplate.active.is_(True),
            )
            .order_by(
                WarehouseRackTemplate.name,
                WarehouseRackTemplate.id,
                WarehouseRackTemplateVersion.version.desc(),
                WarehouseRackTemplateVersion.id.desc(),
            )
            .offset(page_offset)
            .limit(page_limit + 1)
        )
    ).all()
    seen: set[int] = set()
    items = []
    for template, version in rows:
        if int(template.id) in seen:
            continue
        seen.add(int(template.id))
        items.append(_template_out(template, version))
    return {
        **page_from_offset(items, limit=page_limit, offset=page_offset).model_dump(),
    }


@router.post("/maps/{warehouse_map_id}/rack-templates", status_code=201)
async def create_rack_template(
    warehouse_map_id: int,
    payload: RackTemplateCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    existing = (
        await db.execute(
            select(WarehouseRackTemplate).where(
                WarehouseRackTemplate.warehouse_map_id == int(warehouse_map_id),
                WarehouseRackTemplate.name == payload.name.strip(),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "Rack template name already exists")
    template = WarehouseRackTemplate(
        warehouse_map_id=int(warehouse_map_id),
        name=payload.name.strip(),
        rack_type=payload.rack_type.strip(),
        description=payload.description,
    )
    db.add(template)
    await db.flush()
    version = _version_from_payload(template_id=int(template.id), version=1, payload=payload)
    db.add(version)
    await db.commit()
    await db.refresh(template)
    await db.refresh(version)
    return _template_out(template, version)


@router.get(
    "/maps/{warehouse_map_id}/rack-templates/{template_id}/versions",
    response_model=RackTemplatePage,
)
async def list_rack_template_versions(
    warehouse_map_id: int,
    template_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    template = await db.get(WarehouseRackTemplate, int(template_id))
    if template is None or template.warehouse_map_id != int(warehouse_map_id):
        raise HTTPException(404, "Rack template not found")
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    versions = (
        (
            await db.execute(
                select(WarehouseRackTemplateVersion)
                .where(WarehouseRackTemplateVersion.template_id == int(template_id))
                .order_by(
                    WarehouseRackTemplateVersion.version.desc(),
                    WarehouseRackTemplateVersion.id.desc(),
                )
                .offset(page_offset)
                .limit(page_limit + 1)
            )
        )
        .scalars()
        .all()
    )
    items = [
            template_summary(template, version) | {"status": version.status}
            for version in versions
        ]
    return page_from_offset(items, limit=page_limit, offset=page_offset).model_dump()


@router.post("/maps/{warehouse_map_id}/rack-templates/{template_id}/versions", status_code=201)
async def create_rack_template_version(
    warehouse_map_id: int,
    template_id: int,
    payload: RackTemplateVersionCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    template = await db.get(WarehouseRackTemplate, int(template_id))
    if template is None or template.warehouse_map_id != int(warehouse_map_id):
        raise HTTPException(404, "Rack template not found")
    next_version = int(
        (
            await db.execute(
                select(func.coalesce(func.max(WarehouseRackTemplateVersion.version), 0)).where(
                    WarehouseRackTemplateVersion.template_id == int(template_id)
                )
            )
        ).scalar_one()
    ) + 1
    if payload.status == "active":
        await db.execute(
            update(WarehouseRackTemplateVersion)
            .where(
                WarehouseRackTemplateVersion.template_id == int(template_id),
                WarehouseRackTemplateVersion.status == "active",
            )
            .values(status="superseded", superseded_at=datetime.now(UTC))
        )
    version = _version_from_payload(
        template_id=int(template_id),
        version=next_version,
        payload=payload,
        status=payload.status,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return template_summary(template, version) | {"status": version.status}


async def _draft_layout(
    db: AsyncSession,
    warehouse_map_id: int,
    version: int,
) -> WarehouseLayoutVersion:
    layout = (
        await db.execute(
            select(WarehouseLayoutVersion).where(
                WarehouseLayoutVersion.warehouse_map_id == int(warehouse_map_id),
                WarehouseLayoutVersion.version == int(version),
            )
        )
    ).scalar_one_or_none()
    if layout is None:
        raise HTTPException(404, "Warehouse layout version not found")
    return layout


@router.post(
    "/maps/{warehouse_map_id}/layout-versions/{version}/racks/{rack_id}/template-assignment"
)
async def assign_template_to_rack(
    warehouse_map_id: int,
    version: int,
    rack_id: int,
    payload: RackTemplateAssignIn,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _draft_layout(db, warehouse_map_id, version)
    require_draft_revision(layout, parse_revision(if_match, payload.revision))
    row = (
        await db.execute(
            select(WarehouseRack, WarehouseAisle)
            .join(WarehouseAisle, WarehouseRack.aisle_id == WarehouseAisle.id)
            .where(
                WarehouseRack.id == int(rack_id),
                WarehouseAisle.layout_version_id == int(layout.id),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Rack not found in layout")
    rack, _aisle = row
    template_row = (
        await db.execute(
            select(WarehouseRackTemplate, WarehouseRackTemplateVersion)
            .join(
                WarehouseRackTemplateVersion,
                WarehouseRackTemplateVersion.template_id == WarehouseRackTemplate.id,
            )
            .where(
                WarehouseRackTemplate.warehouse_map_id == int(warehouse_map_id),
                WarehouseRackTemplateVersion.id == int(payload.template_version_id),
                WarehouseRackTemplate.active.is_(True),
                WarehouseRackTemplateVersion.status.in_(("active", "draft")),
            )
        )
    ).one_or_none()
    if template_row is None:
        raise HTTPException(404, "Rack template version not found")
    template, template_version = template_row
    shelves = (
        (
            await db.execute(
                select(WarehouseShelf)
                .where(WarehouseShelf.rack_id == int(rack.id))
                .order_by(WarehouseShelf.level)
            )
        )
        .scalars()
        .all()
    )
    bins = (
        (
            await db.execute(
                select(WarehouseBin)
                .where(WarehouseBin.shelf_id.in_([int(shelf.id) for shelf in shelves] or [-1]))
                .order_by(WarehouseBin.code)
            )
        )
        .scalars()
        .all()
    )
    bins_by_shelf: dict[int, list[WarehouseBin]] = {}
    for bin_row in bins:
        bins_by_shelf.setdefault(int(bin_row.shelf_id), []).append(bin_row)
    result = apply_template_to_rack_geometry(
        rack=rack,
        shelves=list(shelves),
        bins_by_shelf=bins_by_shelf,
        template=template,
        version=template_version,
    )
    rack.provenance_status = "manual"
    revision = bump_revision(layout)
    await db.commit()
    return {"revision": revision, "rack_id": int(rack.id), **result}
