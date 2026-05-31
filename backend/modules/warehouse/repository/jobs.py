from __future__ import annotations

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


@dataclass
class WarehouseModelVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime


class WarehouseJobMixin:
    async def next_model_version(self, db: AsyncSession, *, warehouse_map_id: int) -> int:
        max_version = (
            await db.execute(
                select(func.max(WarehouseModel.version)).where(
                    WarehouseModel.warehouse_map_id == warehouse_map_id
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
        # Serialize version allocation per warehouse map.  Without this lock two
        # concurrent persistence jobs can both see the same max(version) and trip
        # uq_warehouse_model_version during flush.
        await db.execute(
            select(WarehouseMap.id)
            .where(WarehouseMap.id == warehouse_map_id)
            .with_for_update()
        )
        version = await self.next_model_version(db, warehouse_map_id=warehouse_map_id)
        model = WarehouseModel(
            warehouse_map_id=warehouse_map_id,
            version=version,
            status="processing",
        )
        db.add(model)
        await db.flush()
        params = {
            "warehouse_map_id": warehouse_map_id,
            "processor": "warehouse_scan",
            "input_source": input_source,
            "capture_result": capture_result,
            "reference_mapping_job_id": reference_mapping_job_id,
            "flight_id": flight_id,
        }
        job = WarehouseMappingJob(
            warehouse_map_id=warehouse_map_id,
            model_id=model.id,
            status="processing",
            progress=5,
            processor=input_source,
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
        job.processor_task_id = task_id
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
                .where(WarehouseMappingJob.id == job_id)
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
        job.status = status
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
        type_map = {
            "textured_mesh_3dtiles": "TILESET_3D",
            "mesh_glb": "MESH_GLB",
            "point_cloud": "POINT_CLOUD",
            "esdf": "ESDF",
            "tsdf": "TSDF",
            "rosbag": "ROSBAG",
            "quality_report": "QUALITY_REPORT",
        }
        for key, url in uploaded.items():
            db.add(
                WarehouseAsset(
                    model_id=model_id,
                    type=type_map.get(key, key.upper()),
                    url=url,
                    size_bytes=artifact_meta.get(key, {}).get("size_bytes"),
                    meta_data={
                        "job_id": job_id,
                        "artifact_key": key,
                        "capture_result": capture_result,
                        "reference_mapping_job_id": reference_mapping_job_id,
                        "flight_id": flight_id,
                        **artifact_meta.get(key, {}),
                    },
                )
            )

    async def mark_job_ready(
        self, db: AsyncSession, *, job: WarehouseMappingJob, model: WarehouseModel
    ) -> None:
        job.status = "ready"
        job.progress = 100
        job.error = None
        job.finished_at = datetime.now(UTC)
        model.status = "ready"

    async def mark_job_failed(
        self,
        db: AsyncSession,
        *,
        job: WarehouseMappingJob,
        model: WarehouseModel,
        error: str,
    ) -> None:
        job.status = "failed"
        job.progress = 100
        job.error = error
        job.finished_at = datetime.now(UTC)
        model.status = "failed"

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
            or_(WarehouseMap.owner_id == owner_id, WarehouseMap.org_id == org_id)
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == owner_id
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
            .limit(limit)
        )
        if warehouse_map_id is not None:
            stmt = stmt.where(WarehouseMap.id == warehouse_map_id)
        return (await db.execute(stmt)).all()

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
            or_(WarehouseMap.owner_id == owner_id, WarehouseMap.org_id == org_id)
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == owner_id
        )
        row = (
            await db.execute(
                select(WarehouseMappingJob, WarehouseMap, WarehouseModel)
                .join(WarehouseMap, WarehouseMappingJob.warehouse_map_id == WarehouseMap.id)
                .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
                .where(
                    WarehouseMappingJob.id == job_id,
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
        if not model_ids:
            return []
        return (
            (
                await db.execute(
                    select(WarehouseAsset)
                    .where(WarehouseAsset.model_id.in_(model_ids))
                    .order_by(WarehouseAsset.model_id.asc(), WarehouseAsset.id.asc())
                )
            )
            .scalars()
            .all()
        )

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
                    .where(WarehouseModel.warehouse_map_id == warehouse_map_id)
                    .order_by(WarehouseModel.version.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            WarehouseModelVersionEntry(
                id=m.id,
                version=m.version,
                status=m.status,
                created_at=m.created_at,
            )
            for m in models
        ]
