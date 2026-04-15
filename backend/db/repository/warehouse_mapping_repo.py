from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    WarehouseAsset,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
)


class WarehouseRepositoryError(RuntimeError):
    pass


@dataclass
class WarehouseModelVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime


class WarehouseMappingRepository:
    async def get_owned_warehouse_map(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
    ) -> WarehouseMap | None:
        scope = (
            or_(WarehouseMap.owner_id == owner_id, WarehouseMap.org_id == org_id)
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == owner_id
        )
        return (
            await db.execute(
                select(WarehouseMap).where(WarehouseMap.id == warehouse_map_id, scope)
            )
        ).scalar_one_or_none()

    async def list_warehouse_maps(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
        limit: int = 100,
    ) -> list[WarehouseMap]:
        scope = (
            or_(WarehouseMap.owner_id == owner_id, WarehouseMap.org_id == org_id)
            if allow_org_access and org_id is not None
            else WarehouseMap.owner_id == owner_id
        )
        return (
            (
                await db.execute(
                    select(WarehouseMap)
                    .where(scope)
                    .order_by(WarehouseMap.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def delete_warehouse_map(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
    ) -> bool:
        """Returns True if a row was deleted, False if not found / not owned."""
        warehouse_map = await self.get_owned_warehouse_map(
            db,
            warehouse_map_id=warehouse_map_id,
            owner_id=owner_id,
            org_id=org_id,
            allow_org_access=allow_org_access,
        )
        if warehouse_map is None:
            return False
        await db.delete(warehouse_map)
        return True

    # ------------------------------------------------------------------ docks

    async def list_dock_stations(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
    ) -> list[WarehouseDockStation]:
        return (
            (
                await db.execute(
                    select(WarehouseDockStation)
                    .where(
                        WarehouseDockStation.warehouse_map_id == warehouse_map_id,
                        WarehouseDockStation.active.is_(True),
                    )
                    .order_by(WarehouseDockStation.id.asc())
                )
            )
            .scalars()
            .all()
        )

    async def create_dock_station(
        self,
        db: AsyncSession,
        *,
        warehouse_map_id: int,
        name: str,
        pose_local_json: dict[str, Any],
        entry_pose_local_json: dict[str, Any],
        exit_pose_local_json: dict[str, Any],
        marker_id: str | None = None,
        charger_type: str | None = None,
        meta_data: dict[str, Any] | None = None,
    ) -> WarehouseDockStation:
        dock = WarehouseDockStation(
            warehouse_map_id=warehouse_map_id,
            name=name.strip(),
            marker_id=marker_id,
            charger_type=charger_type,
            pose_local_json=dict(pose_local_json),
            entry_pose_local_json=dict(entry_pose_local_json),
            exit_pose_local_json=dict(exit_pose_local_json),
            meta_data=dict(meta_data or {}),
            active=True,
        )
        db.add(dock)
        await db.flush()
        return dock

    async def deactivate_dock_station(
        self,
        db: AsyncSession,
        *,
        dock_id: int,
        warehouse_map_id: int,
    ) -> bool:
        dock = (
            await db.execute(
                select(WarehouseDockStation).where(
                    WarehouseDockStation.id == dock_id,
                    WarehouseDockStation.warehouse_map_id == warehouse_map_id,
                )
            )
        ).scalar_one_or_none()
        if dock is None:
            return False
        dock.active = False
        return True

    async def create_warehouse_map(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None,
        project_id: int | None,
        warehouse_name: str,
        polygon_local_m: list[tuple[float, float]],
        meta_data: dict[str, Any] | None = None,
    ) -> WarehouseMap:
        """Create a warehouse map defined by a local metric polygon (no GPS)."""
        if len(polygon_local_m) < 3:
            raise WarehouseRepositoryError("Warehouse polygon requires at least 3 points.")
        # Compute area from the local polygon directly (metres²)
        from shapely.geometry import Polygon as _Polygon

        try:
            area_m2 = float(_Polygon(polygon_local_m).area)
        except Exception:
            area_m2 = None

        base_meta = dict(meta_data or {})
        base_meta["polygon_local_m"] = [[float(x), float(y)] for x, y in polygon_local_m]

        warehouse_map = WarehouseMap(
            owner_id=owner_id,
            org_id=org_id,
            project_id=project_id,
            name=warehouse_name.strip(),
            boundary=None,  # indoor — no GPS boundary
            centroid=None,
            area_m2=area_m2,
            meta_data=base_meta,
        )
        db.add(warehouse_map)
        await db.flush()
        return warehouse_map

    async def get_or_create_warehouse_map(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None,
        project_id: int | None,
        warehouse_map_id: int | None,
        warehouse_name: str | None,
        polygon_local_m: list[tuple[float, float]],
        meta_data: dict[str, Any] | None = None,
    ) -> WarehouseMap:
        if warehouse_map_id is not None:
            warehouse_map = await self.get_owned_warehouse_map(
                db,
                warehouse_map_id=int(warehouse_map_id),
                owner_id=owner_id,
                org_id=org_id,
                allow_org_access=org_id is not None,
            )
            if warehouse_map is None:
                raise WarehouseRepositoryError("Selected warehouse map was not found.")
            return warehouse_map
        resolved_name = (warehouse_name or "").strip() or self.auto_warehouse_name()
        return await self.create_warehouse_map(
            db,
            owner_id=owner_id,
            org_id=org_id,
            project_id=project_id,
            warehouse_name=resolved_name,
            polygon_local_m=polygon_local_m,
            meta_data=meta_data,
        )

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
    ) -> tuple[WarehouseModel, WarehouseMappingJob]:
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
            "input_source": "warehouse_scan",
            "capture_result": capture_result,
            "reference_mapping_job_id": reference_mapping_job_id,
            "flight_id": flight_id,
        }
        job = WarehouseMappingJob(
            warehouse_map_id=warehouse_map_id,
            model_id=model.id,
            status="processing",
            progress=5,
            processor="warehouse_scan",
            params=params,
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.flush()
        return model, job

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
            "point_cloud": "POINTCLOUD",
        }
        for key, url in uploaded.items():
            db.add(
                WarehouseAsset(
                    model_id=model_id,
                    type=type_map.get(key, key.upper()),
                    url=url,
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

    async def list_ready_scanned_maps(
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
                WarehouseMappingJob.processor == "warehouse_scan",
                WarehouseMappingJob.status == "ready",
                WarehouseModel.status == "ready",
            )
            .order_by(WarehouseMappingJob.id.desc())
            .limit(limit)
        )
        if warehouse_map_id is not None:
            stmt = stmt.where(WarehouseMap.id == warehouse_map_id)
        return (await db.execute(stmt)).all()

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

    @staticmethod
    def auto_warehouse_name() -> str:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"Warehouse map {stamp}"

    @staticmethod
    def polygon_from_local(warehouse_map: WarehouseMap) -> list[list[float]]:
        """Return the local polygon [[x_m, y_m], ...] stored in meta_data."""
        meta = warehouse_map.meta_data if isinstance(warehouse_map.meta_data, dict) else {}
        raw = meta.get("polygon_local_m")
        if isinstance(raw, list):
            return [[float(pt[0]), float(pt[1])] for pt in raw if len(pt) >= 2]
        return []
