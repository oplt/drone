from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.database.session import Session
from backend.modules.warehouse.models import WarehouseAsset
from backend.modules.warehouse.repository import WarehouseMappingRepository


class WarehouseScanMappingError(RuntimeError):
    pass


class WarehouseScanMappingService:
    async def persist_capture(
        self,
        *,
        owner_id: int,
        org_id: int | None,
        warehouse_map_id: int | None,
        warehouse_name: str | None,
        polygon_local_m: list[Any],
        session_dir: Path,
        capture_result: dict[str, Any],
        reference_mapping_job_id: int | None,
        flight_id: int | None,
        input_source: str = "warehouse_scan",
    ) -> dict[str, Any]:
        del owner_id, org_id, warehouse_name, polygon_local_m
        if warehouse_map_id is None:
            raise WarehouseScanMappingError("warehouse_map_id is required.")
        if not session_dir.exists():
            raise WarehouseScanMappingError(f"Capture session directory is missing: {session_dir}")
        files = [p for p in session_dir.rglob("*") if p.is_file()]
        if not files:
            raise WarehouseScanMappingError(f"No mapping artifacts found in {session_dir}")

        repo = WarehouseMappingRepository()
        async with Session() as db:
            try:
                model, job = await repo.create_mapping_job(
                    db,
                    warehouse_map_id=int(warehouse_map_id),
                    capture_result=capture_result,
                    reference_mapping_job_id=reference_mapping_job_id,
                    flight_id=flight_id,
                    input_source=input_source,
                )
                for file_path in files:
                    db.add(
                        WarehouseAsset(
                            model_id=model.id,
                            type=_asset_type(file_path),
                            url=str(file_path),
                            size_bytes=file_path.stat().st_size,
                            meta_data={
                                "job_id": job.id,
                                "artifact_key": file_path.suffix.lower().lstrip(".") or "file",
                                "capture_result": capture_result,
                            },
                        )
                    )
                await repo.mark_job_ready(db, job=job, model=model)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                raise WarehouseScanMappingError(str(exc)) from exc
        return {
            "warehouse_map_id": int(warehouse_map_id),
            "model_id": int(model.id),
            "job_id": int(job.id),
            "artifact_count": len(files),
            "status": "ready",
        }


def _asset_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".db3", ".mcap", ".bag"}:
        return "ROSBAG"
    if suffix in {".ply", ".pcd"}:
        return "POINT_CLOUD"
    if suffix == ".glb":
        return "MESH_GLB"
    if suffix == ".json":
        return "QUALITY_REPORT"
    return "WAREHOUSE_ARTIFACT"

