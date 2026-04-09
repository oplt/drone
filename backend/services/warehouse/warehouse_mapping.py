from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.db.repository.warehouse_mapping_repo import (
    WarehouseMappingRepository,
    WarehouseRepositoryError,
)
from backend.db.session import Session
from backend.services.photogrammetry.storage import StorageService
from backend.services.photogrammetry.tiling import convert_mesh_to_3dtiles

logger = logging.getLogger(__name__)

_MESH_EXTENSIONS = (".glb", ".gltf", ".obj", ".ply", ".fbx", ".dae", ".stl")
_POINTCLOUD_EXTENSIONS = (".pcd", ".las", ".laz", ".e57", ".ply")


class WarehouseScanMappingError(RuntimeError):
    pass


class WarehouseScanMappingService:
    def __init__(self) -> None:
        self.storage = StorageService()
        self.repo = WarehouseMappingRepository()

    async def persist_capture(
        self,
        *,
        owner_id: int,
        warehouse_map_id: int | None,
        warehouse_name: str | None,
        polygon_local_m: list[tuple[float, float]],
        session_dir: str | Path,
        capture_result: dict[str, Any],
        reference_mapping_job_id: int | None = None,
        flight_id: int | None = None,
    ) -> dict[str, Any]:
        resolved_session_dir = Path(session_dir).resolve()
        if not resolved_session_dir.exists():
            raise WarehouseScanMappingError(
                f"Warehouse capture directory does not exist: {resolved_session_dir}"
            )

        async with Session() as db:
            try:
                warehouse_map = await self.repo.get_or_create_warehouse_map(
                    db,
                    owner_id=owner_id,
                    warehouse_map_id=warehouse_map_id,
                    warehouse_name=warehouse_name,
                    polygon_local_m=polygon_local_m,
                    meta_data={
                        "source": "warehouse_scan",
                        "reference_mapping_job_id": reference_mapping_job_id,
                    },
                )
                model, job = await self.repo.create_mapping_job(
                    db,
                    warehouse_map_id=int(warehouse_map.id),
                    capture_result=capture_result,
                    reference_mapping_job_id=reference_mapping_job_id,
                    flight_id=flight_id,
                )
                await db.commit()
            except WarehouseRepositoryError as exc:
                await db.rollback()
                raise WarehouseScanMappingError(str(exc)) from exc

        try:
            with tempfile.TemporaryDirectory(prefix=f"warehouse-map-{job.id}-") as tmp_dir:
                work_dir = Path(tmp_dir)
                converted, artifact_meta = await asyncio.to_thread(
                    self._prepare_artifacts,
                    resolved_session_dir,
                    work_dir,
                    polygon_local_m,
                )
                uploaded = await self._upload_outputs(converted)

            async with Session() as db:
                db_job = await db.get(type(job), int(job.id))
                db_model = await db.get(type(model), int(model.id))
                if db_job is None or db_model is None:
                    raise WarehouseScanMappingError(
                        "Warehouse mapping job disappeared before asset registration."
                    )
                await self.repo.add_assets(
                    db,
                    model_id=int(db_model.id),
                    uploaded=uploaded,
                    artifact_meta=artifact_meta,
                    capture_result=capture_result,
                    reference_mapping_job_id=reference_mapping_job_id,
                    flight_id=flight_id,
                    job_id=int(db_job.id),
                )
                await self.repo.mark_job_ready(db, job=db_job, model=db_model)
                await db.commit()
            return {
                "warehouse_map_id": int(warehouse_map.id),
                "job_id": int(job.id),
                "model_id": int(model.id),
                "assets": uploaded,
            }
        except Exception as exc:
            async with Session() as db:
                db_job = await db.get(type(job), int(job.id))
                db_model = await db.get(type(model), int(model.id))
                if db_job is not None and db_model is not None:
                    await self.repo.mark_job_failed(db, job=db_job, model=db_model, error=str(exc))
                    await db.commit()
            raise

    async def _upload_outputs(self, converted: dict[str, str]) -> dict[str, str]:
        async def _upload_one(key: str, path: str) -> tuple[str, str]:
            src = Path(path).resolve()
            if src.is_dir():
                url = await self.storage.upload_directory(str(src))
            else:
                url = await self.storage.upload_file(str(src))
            return key, url

        if not converted:
            return {}

        # return_exceptions=True so one failed upload doesn't discard all others
        results = await asyncio.gather(
            *[_upload_one(key, path) for key, path in converted.items()],
            return_exceptions=True,
        )
        uploaded: dict[str, str] = {}
        errors: list[str] = []
        for result in results:
            if isinstance(result, BaseException):
                errors.append(str(result))
                logger.error("Warehouse asset upload failed: %s", result)
            else:
                key, url = result
                uploaded[key] = url

        if not uploaded:
            raise WarehouseScanMappingError(
                "All warehouse artifact uploads failed. Errors: " + "; ".join(errors)
            )
        if errors:
            logger.warning(
                "Warehouse upload partial failure (%d/%d succeeded). Errors: %s",
                len(uploaded),
                len(converted),
                "; ".join(errors),
            )
        return uploaded

    @staticmethod
    def _bbox_from_polygon_local_m(
        polygon_local_m: list[tuple[float, float]],
    ) -> dict[str, float]:
        xs = [float(x) for x, _y in polygon_local_m]
        ys = [float(y) for _x, y in polygon_local_m]
        return {
            "x_min_m": min(xs),
            "y_min_m": min(ys),
            "x_max_m": max(xs),
            "y_max_m": max(ys),
        }

    @staticmethod
    def _find_existing_tileset_dir(root: Path) -> Path | None:
        candidates = sorted(root.rglob("tileset.json"), key=lambda path: len(path.parts))
        return candidates[0].parent if candidates else None

    @staticmethod
    def _find_first_file(root: Path, extensions: Iterable[str]) -> Path | None:
        allowed = {ext.lower() for ext in extensions}
        candidates = [
            path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in allowed
        ]
        candidates.sort(key=lambda path: (len(path.parts), path.name.lower()))
        return candidates[0] if candidates else None

    @staticmethod
    def _copy_to_work_dir(src: Path, work_dir: Path) -> Path:
        dst = work_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst

    def _run_postprocess_cmd(self, *, input_dir: Path, output_dir: Path) -> bool:
        template = os.getenv("WAREHOUSE_SCAN_POSTPROCESS_CMD", "").strip()
        if not template:
            return False
        cmd = template.format(input_dir=str(input_dir), output_dir=str(output_dir))
        logger.info("Running warehouse post-process command: %s", cmd)
        subprocess.run(cmd, shell=True, check=True)
        return True

    def _prepare_artifacts(
        self,
        session_dir: Path,
        work_dir: Path,
        polygon_local_m: list[tuple[float, float]],
    ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        converted: dict[str, str] = {}
        artifact_meta: dict[str, dict[str, Any]] = {}

        tileset_dir = self._find_existing_tileset_dir(session_dir)
        if tileset_dir is None:
            postprocess_output = work_dir / "postprocess_output"
            postprocess_output.mkdir(parents=True, exist_ok=True)
            ran_postprocess = self._run_postprocess_cmd(
                input_dir=session_dir,
                output_dir=postprocess_output,
            )
            search_root = postprocess_output if ran_postprocess else session_dir
            tileset_dir = self._find_existing_tileset_dir(search_root)
        if tileset_dir is not None:
            converted["textured_mesh_3dtiles"] = str(tileset_dir)
            artifact_meta["textured_mesh_3dtiles"] = {
                "bbox": self._bbox_from_polygon_local_m(polygon_local_m),
            }
        else:
            mesh_src = self._find_first_file(session_dir, _MESH_EXTENSIONS)
            if mesh_src is not None:
                mesh_local = self._copy_to_work_dir(mesh_src, work_dir)
                tiles_dir = work_dir / "tileset"
                convert_mesh_to_3dtiles(str(mesh_local), str(tiles_dir))
                converted["textured_mesh_3dtiles"] = str(tiles_dir)
                artifact_meta["textured_mesh_3dtiles"] = {
                    "source_mesh": mesh_src.name,
                    "bbox": self._bbox_from_polygon_local_m(polygon_local_m),
                }

        pointcloud_src = self._find_first_file(session_dir, _POINTCLOUD_EXTENSIONS)
        if pointcloud_src is not None:
            pointcloud_local = self._copy_to_work_dir(pointcloud_src, work_dir)
            converted["point_cloud"] = str(pointcloud_local)
            artifact_meta["point_cloud"] = {
                "source_point_cloud": pointcloud_src.name,
                "bbox": self._bbox_from_polygon_local_m(polygon_local_m),
            }

        if not converted:
            raise WarehouseScanMappingError(
                "Warehouse capture did not produce a tileset or point cloud artifact."
            )
        return converted, artifact_meta
