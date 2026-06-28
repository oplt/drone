from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
)


class WarehouseRepositoryError(RuntimeError):
    pass


WAREHOUSE_SCANNED_MAP_PROCESSORS = (
    "warehouse_scan",
    "warehouse_manual_mapping",
    "indoor_exploration",
    "simulation",
)

_ASSET_TYPE_MAP = {
    "textured_mesh_3dtiles": "TILESET_3D",
    "mesh_glb": "MESH_GLB",
    "point_cloud": "POINT_CLOUD",
    "esdf": "ESDF",
    "tsdf": "TSDF",
    "rosbag": "ROSBAG",
    "quality_report": "QUALITY_REPORT",
}
_MAX_LIST_LIMIT = 500
_IN_CHUNK_SIZE = 1_000
_MAX_ERROR_LENGTH = 2_000


@dataclass(slots=True)
class WarehouseModelVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime


def _clamp_limit(limit: int, *, default: int = 50, max_limit: int = _MAX_LIST_LIMIT) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(max_limit, value))


def _clean_processor(value: str | None) -> str:
    processor = (value or "warehouse_scan").strip() or "warehouse_scan"
    if processor not in WAREHOUSE_SCANNED_MAP_PROCESSORS:
        raise WarehouseRepositoryError(f"Unsupported warehouse map processor: {processor}")
    return processor


def _json_object(value: dict[str, Any] | None, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WarehouseRepositoryError(f"{field_name} must be a JSON object.")
    return dict(value)


def _chunks(values: list[int], size: int = _IN_CHUNK_SIZE) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


class WarehouseJobMixin:
    async def next_model_version(self, db: AsyncSession, *, warehouse_map_id: int) -> int:
        max_version = (
            await db.execute(
                select(func.max(WarehouseModel.version)).where(
                    WarehouseModel.warehouse_map_id == int(warehouse_map_id)
                )
            )
        ).scalar_one()
        return int(max_version or 0) + 1

    async def create_mapping_job(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        capture_result: dict[str, Any],
        reference_mapping_job_id: int | None,
        flight_id: int | None,
        input_source: str = "warehouse_scan",
    ) -> tuple[WarehouseModel, WarehouseMappingJob]:
        processor = _clean_processor(input_source)
        capture_payload = _json_object(capture_result, field_name="capture_result")

        # Serialize version allocation per warehouse map. Without this lock two
        # concurrent persistence jobs can both see the same max(version) and trip
        # uq_warehouse_model_version during flush.
        locked_map_id = await db.scalar(
            select(WarehouseMap.id)
            .where(WarehouseMap.id == int(warehouse_map_id))
            .with_for_update()
        )
        if locked_map_id is None:
            raise WarehouseRepositoryError("Warehouse map was not found.")

        version = await self.next_model_version(db, warehouse_map_id=int(warehouse_map_id))
        model = WarehouseModel(
            warehouse_map_id=int(warehouse_map_id),
            version=version,
            status="processing",
        )
        db.add(model)
        await db.flush()

        params = {
            "warehouse_map_id": int(warehouse_map_id),
            "processor": processor,
            "input_source": processor,
            "capture_result": capture_payload,
            "reference_mapping_job_id": reference_mapping_job_id,
            "flight_id": flight_id,
        }
        job = WarehouseMappingJob(
            warehouse_map_id=int(warehouse_map_id),
            model_id=model.id,
            status="processing",
            progress=5,
            processor=processor,
            params=params,
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.flush()
        return model, job

    async def set_job_task_id(
        self,
        db: AsyncSession,
        *,
        job: WarehouseMappingJob,
        task_id: str,
    ) -> None:
        cleaned_task_id = str(task_id or "").strip()
        if not cleaned_task_id:
            raise WarehouseRepositoryError("task_id cannot be empty.")
        job.processor_task_id = cleaned_task_id
        job.status = "processing"
        job.progress = max(int(job.progress or 0), 10)
        await db.flush()

    async def get_job_with_model(
        self,
        db: AsyncSession,
        *,
        job_id: int,
    ) -> tuple[WarehouseMappingJob, WarehouseModel] | None:
        row = (
            await db.execute(
                select(WarehouseMappingJob, WarehouseModel)
                .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
                .where(WarehouseMappingJob.id == int(job_id))
            )
        ).first()
        return row if row is None else (row[0], row[1])

    async def update_job_progress(
        self,
        db: AsyncSession,
        *,
        job: WarehouseMappingJob,
        progress: int,
        status: str = "processing",
    ) -> None:
        job.status = str(status or "processing").strip() or "processing"
        job.progress = max(0, min(100, int(progress)))
        await db.flush()

    async def add_assets(
        self,
        db: AsyncSession,
        *,
        model_id: int,
        uploaded: dict[str, str],
        artifact_meta: dict[str, dict[str, Any]],
        capture_result: dict[str, Any],
        reference_mapping_job_id: int | None,
        flight_id: int | None,
        job_id: int,
    ) -> None:
        if not uploaded:
            return
        capture_payload = _json_object(capture_result, field_name="capture_result")
        assets: list[WarehouseAsset] = []
        for key, url in uploaded.items():
            artifact_key = str(key)
            artifact_url = str(url or "").strip()
            if not artifact_url:
                continue
            metadata = _json_object(
                artifact_meta.get(artifact_key, {}),
                field_name=f"artifact_meta[{artifact_key}]",
            )
            assets.append(
                WarehouseAsset(
                    model_id=int(model_id),
                    frame_id=str(metadata.get("frame_id") or "odom"),
                    type=_ASSET_TYPE_MAP.get(artifact_key, artifact_key.upper()),
                    url=artifact_url,
                    size_bytes=metadata.get("size_bytes"),
                    checksum=(
                        metadata.get("checksum_sha256") or metadata.get("checksum")
                    ),
                    meta_data={
                        "job_id": int(job_id),
                        "artifact_key": artifact_key,
                        "capture_result": capture_payload,
                        "reference_mapping_job_id": reference_mapping_job_id,
                        "flight_id": flight_id,
                        **metadata,
                    },
                )
            )
        if assets:
            db.add_all(assets)
            await db.flush()

    async def mark_job_ready(
        self, db: AsyncSession, *, job: WarehouseMappingJob, model: WarehouseModel
    ) -> None:
        now = datetime.now(UTC)
        job.status = "ready"
        job.progress = 100
        job.error = None
        job.finished_at = now
        model.status = "ready"
        await db.flush()

    async def mark_job_failed(
        self,
        db: AsyncSession,
        *,
        job: WarehouseMappingJob,
        model: WarehouseModel,
        error: str,
    ) -> None:
        now = datetime.now(UTC)
        job.status = "failed"
        job.progress = 100
        job.error = str(error or "")[:_MAX_ERROR_LENGTH]
        job.finished_at = now
        model.status = "failed"
        await db.flush()

    async def list_scanned_maps(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
        warehouse_map_id: int | None = None,
        limit: int = 50,
    ) -> list[tuple[WarehouseMappingJob, WarehouseMap, WarehouseModel]]:
        scope = (
            or_(WarehouseMap.owner_id == int(owner_id), WarehouseMap.org_id == int(org_id))
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == int(owner_id)
        )
        stmt = (
            select(WarehouseMappingJob, WarehouseMap, WarehouseModel)
            .join(WarehouseMap, WarehouseMappingJob.warehouse_map_id == WarehouseMap.id)
            .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
            .where(
                scope,
                WarehouseMappingJob.processor.in_(WAREHOUSE_SCANNED_MAP_PROCESSORS),
                WarehouseMappingJob.status.in_(["queued", "processing", "ready", "failed"]),
                WarehouseModel.status.in_(["processing", "ready", "failed"]),
            )
            .order_by(WarehouseMappingJob.id.desc())
            .limit(_clamp_limit(limit))
        )
        if warehouse_map_id is not None:
            stmt = stmt.where(WarehouseMap.id == int(warehouse_map_id))
        return list((await db.execute(stmt)).all())

    async def delete_scanned_map_by_job_id(
        self,
        db: AsyncSession,
        *,
        job_id: int,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
    ) -> bool:
        scope = (
            or_(WarehouseMap.owner_id == int(owner_id), WarehouseMap.org_id == int(org_id))
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == int(owner_id)
        )
        row = (
            await db.execute(
                select(WarehouseMappingJob, WarehouseMap, WarehouseModel)
                .join(WarehouseMap, WarehouseMappingJob.warehouse_map_id == WarehouseMap.id)
                .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
                .where(
                    WarehouseMappingJob.id == int(job_id),
                    scope,
                    WarehouseMappingJob.processor.in_(WAREHOUSE_SCANNED_MAP_PROCESSORS),
                )
            )
        ).first()
        if row is None:
            return False
        _job, _warehouse_map, model = row
        await db.delete(model)
        await db.flush()
        return True

    async def list_assets_for_models(
        self,
        db: AsyncSession,
        *,
        model_ids: list[int],
    ) -> list[WarehouseAsset]:
        unique_ids = sorted({int(model_id) for model_id in model_ids if model_id is not None})
        if not unique_ids:
            return []

        assets: list[WarehouseAsset] = []
        for batch in _chunks(unique_ids):
            rows = await db.execute(
                select(WarehouseAsset)
                .where(WarehouseAsset.model_id.in_(batch))
                .order_by(WarehouseAsset.model_id.asc(), WarehouseAsset.id.asc())
            )
            assets.extend(rows.scalars().all())
        assets.sort(key=lambda asset: (int(asset.model_id), int(asset.id)))
        return assets

    async def list_versions(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
    ) -> list[WarehouseModelVersionEntry]:
        models = (
            (
                await db.execute(
                    select(WarehouseModel)
                    .where(WarehouseModel.warehouse_map_id == int(warehouse_map_id))
                    .order_by(WarehouseModel.version.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            WarehouseModelVersionEntry(
                id=int(m.id),
                version=int(m.version),
                status=str(m.status),
                created_at=m.created_at,
            )
            for m in models
        ]
