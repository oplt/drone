from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.core.database.session import Session
from backend.infrastructure.photogrammetry.raster_tiling import convert_mesh_to_3dtiles
from backend.infrastructure.photogrammetry.storage import StorageService
from backend.modules.organizations.service import get_default_project
from backend.modules.warehouse.repository import (
    WarehouseMappingRepository,
    WarehouseRepositoryError,
)
from backend.modules.warehouse.service.queue import (
    WarehouseMappingQueue,
    WarehouseMappingQueueError,
)

logger = logging.getLogger(__name__)

_MESH_EXTENSIONS = (".glb", ".gltf", ".obj", ".ply", ".fbx", ".dae", ".stl")
_POINTCLOUD_EXTENSIONS = (".pcd", ".las", ".laz", ".e57", ".ply")
_ROSBAG_EXTENSIONS = (".db3", ".mcap", ".bag")


class WarehouseScanMappingError(RuntimeError):
    pass


class WarehouseScanMappingPreconditionError(WarehouseScanMappingError):
    """Mapping cannot proceed — missing inputs/artifacts; do not retry blindly."""


class WarehouseScanMappingService:
    def __init__(self) -> None:
        self.storage = StorageService()
        self.repo = WarehouseMappingRepository()
        self.queue = WarehouseMappingQueue()

    async def persist_capture(
        self,
        *,
        owner_id: int,
        org_id: int | None,
        warehouse_map_id: int | None,
        warehouse_name: str | None,
        polygon_local_m: list[tuple[float, float]],
        session_dir: str | Path,
        capture_result: dict[str, Any],
        reference_mapping_job_id: int | None = None,
        flight_id: int | None = None,
        source: str = "warehouse_scan",
    ) -> dict[str, Any]:
        resolved_session_dir = Path(session_dir).resolve()
        if not resolved_session_dir.exists():
            raise WarehouseScanMappingError(
                f"Warehouse capture directory does not exist: {resolved_session_dir}"
            )
        if len(polygon_local_m) < 3:
            raise WarehouseScanMappingError(
                "Warehouse mapping requires polygon_local_m with at least 3 points."
            )
        capture_result = dict(capture_result)
        capture_result.setdefault("absolute_dir", str(resolved_session_dir))
        meta = capture_result.get("meta")
        capture_result["meta"] = {
            **(meta if isinstance(meta, dict) else {}),
            "polygon_local_m": [[float(x), float(y)] for x, y in polygon_local_m],
        }

        async with Session() as db:
            try:
                default_project = (
                    await get_default_project(db, org_id=int(org_id))
                    if org_id is not None
                    else None
                )
                warehouse_map = await self.repo.get_or_create_warehouse_map(
                    db,
                    owner_id=owner_id,
                    org_id=org_id,
                    project_id=default_project.id if default_project else None,
                    warehouse_map_id=warehouse_map_id,
                    warehouse_name=warehouse_name,
                    polygon_local_m=polygon_local_m,
                    meta_data={
                        "source": source,
                        "reference_mapping_job_id": reference_mapping_job_id,
                    },
                )
                model, job = await self.repo.create_mapping_job(
                    db,
                    warehouse_map_id=int(warehouse_map.id),
                    capture_result=capture_result,
                    reference_mapping_job_id=reference_mapping_job_id,
                    flight_id=flight_id,
                    input_source=source,
                )
                warehouse_map_id_out = int(warehouse_map.id)
                model_id = int(model.id)
                job_id = int(job.id)
                await db.commit()
                try:
                    task_id = self.queue.enqueue(job_id=job_id)
                except WarehouseMappingQueueError:
                    logger.exception("Warehouse mapping enqueue failed; job remains processing")
                    task_id = ""
                if task_id:
                    await self.repo.set_job_task_id(db, job=job, task_id=task_id)
                status_out = str(job.status)
                processor_task_id_out = job.processor_task_id
                await db.commit()
            except WarehouseRepositoryError as exc:
                await db.rollback()
                raise WarehouseScanMappingError(str(exc)) from exc
        return {
            "warehouse_map_id": warehouse_map_id_out,
            "job_id": job_id,
            "model_id": model_id,
            "status": status_out,
            "processor_task_id": processor_task_id_out,
            "assets": {},
        }

    async def process_job(self, *, job_id: int) -> dict[str, Any]:
        async with Session() as db:
            row = await self.repo.get_job_with_model(db, job_id=job_id)
            if row is None:
                raise WarehouseScanMappingError(f"Warehouse mapping job not found: {job_id}")
            job, model = row
            model_id = int(model.id)
            job_model_type = type(job)
            model_type = type(model)
            await self.repo.update_job_progress(db, job=job, progress=20)
            await db.commit()
            params = dict(job.params or {})

        capture_result = params.get("capture_result")
        if not isinstance(capture_result, dict):
            raise WarehouseScanMappingError("Warehouse mapping job has no capture_result.")
        session_dir = Path(str(capture_result.get("absolute_dir") or "")).resolve()
        meta = capture_result.get("meta")
        polygon_raw = meta.get("polygon_local_m") if isinstance(meta, dict) else None
        polygon_local_m = self._polygon_from_raw(polygon_raw)
        reference_mapping_job_id = params.get("reference_mapping_job_id")
        flight_id = params.get("flight_id")

        try:
            with tempfile.TemporaryDirectory(prefix=f"warehouse-map-{job_id}-") as tmp_dir:
                work_dir = Path(tmp_dir)
                converted, artifact_meta = await asyncio.to_thread(
                    self._prepare_artifacts,
                    session_dir,
                    work_dir,
                    polygon_local_m,
                )
                uploaded = await self._upload_outputs(converted)

            async with Session() as db:
                db_job = await db.get(job_model_type, job_id)
                db_model = await db.get(model_type, model_id)
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
                "job_id": int(job_id),
                "model_id": model_id,
                "assets": uploaded,
            }
        except Exception as exc:
            async with Session() as db:
                db_job = await db.get(job_model_type, job_id)
                db_model = await db.get(model_type, model_id)
                if db_job is not None and db_model is not None:
                    await self.repo.mark_job_failed(db, job=db_job, model=db_model, error=str(exc))
                    await db.commit()
            raise

    @staticmethod
    def _polygon_from_raw(raw: object) -> list[tuple[float, float]]:
        if not isinstance(raw, list) or len(raw) < 3:
            raise WarehouseScanMappingError("Warehouse mapping job has invalid polygon_local_m.")
        points: list[tuple[float, float]] = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                raise WarehouseScanMappingError("Warehouse mapping job has invalid polygon point.")
            points.append((float(item[0]), float(item[1])))
        return points

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

    @staticmethod
    def _read_manifest(session_dir: Path) -> dict[str, Any]:
        for name in ("warehouse_mapping_manifest.json", "capture_manifest.json"):
            path = session_dir / name
            if not path.exists() or not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
            return payload if isinstance(payload, dict) else {}
        return {}

    @staticmethod
    def _manifest_asset_path(
        session_dir: Path,
        manifest: dict[str, Any],
        *keys: str,
    ) -> Path | None:
        assets = manifest.get("assets")
        if not isinstance(assets, dict):
            return None
        for key in keys:
            raw = assets.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            path = (session_dir / raw).resolve()
            try:
                path.relative_to(session_dir.resolve())
            except ValueError:
                logger.warning("Ignoring manifest asset outside session dir: %s", path)
                continue
            if path.exists():
                return path
        return None

    def _run_postprocess_cmd(self, *, input_dir: Path, output_dir: Path) -> bool:
        template = os.getenv("WAREHOUSE_SCAN_POSTPROCESS_CMD", "").strip()
        if not template:
            return False
        rendered = template.format(input_dir=str(input_dir), output_dir=str(output_dir))
        argv = shlex.split(rendered)
        if not argv:
            return False
        logger.info("Running warehouse post-process command: %s", argv[0])
        subprocess.run(argv, check=True)
        return True

    def _prepare_artifacts(
        self,
        session_dir: Path,
        work_dir: Path,
        polygon_local_m: list[tuple[float, float]],
    ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        converted: dict[str, str] = {}
        artifact_meta: dict[str, dict[str, Any]] = {}
        manifest = self._read_manifest(session_dir)

        tileset_dir = self._manifest_asset_path(session_dir, manifest, "tileset", "tileset_dir")
        if tileset_dir is not None and tileset_dir.is_file():
            tileset_dir = tileset_dir.parent
        if tileset_dir is None:
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
            mesh_src = self._manifest_asset_path(session_dir, manifest, "mesh_glb", "mesh")
            if mesh_src is None:
                mesh_src = self._find_first_file(session_dir, _MESH_EXTENSIONS)
            if mesh_src is not None:
                mesh_local = self._copy_to_work_dir(mesh_src, work_dir)
                if mesh_local.suffix.lower() in {".glb", ".gltf"}:
                    converted["mesh_glb"] = str(mesh_local)
                    artifact_meta["mesh_glb"] = {
                        "source_mesh": mesh_src.name,
                        "size_bytes": mesh_src.stat().st_size,
                    }
                tiles_dir = work_dir / "tileset"
                convert_mesh_to_3dtiles(str(mesh_local), str(tiles_dir))
                converted["textured_mesh_3dtiles"] = str(tiles_dir)
                artifact_meta["textured_mesh_3dtiles"] = {
                    "source_mesh": mesh_src.name,
                    "bbox": self._bbox_from_polygon_local_m(polygon_local_m),
                }

        pointcloud_src = self._manifest_asset_path(session_dir, manifest, "point_cloud")
        if pointcloud_src is None:
            pointcloud_src = self._find_first_file(session_dir, _POINTCLOUD_EXTENSIONS)
        if pointcloud_src is not None:
            pointcloud_local = self._copy_to_work_dir(pointcloud_src, work_dir)
            converted["point_cloud"] = str(pointcloud_local)
            artifact_meta["point_cloud"] = {
                "source_point_cloud": pointcloud_src.name,
                "size_bytes": pointcloud_src.stat().st_size,
                "bbox": self._bbox_from_polygon_local_m(polygon_local_m),
            }

        rosbag_src = self._manifest_asset_path(session_dir, manifest, "rosbag")
        if rosbag_src is None:
            rosbag_src = self._find_first_file(session_dir, _ROSBAG_EXTENSIONS)
        if rosbag_src is not None:
            rosbag_local = self._copy_to_work_dir(rosbag_src, work_dir)
            converted["rosbag"] = str(rosbag_local)
            artifact_meta["rosbag"] = {
                "source_rosbag": rosbag_src.name,
                "size_bytes": rosbag_src.stat().st_size,
            }

        quality_src = self._manifest_asset_path(session_dir, manifest, "quality_report")
        if quality_src is None:
            quality_src = session_dir / "mapping_quality_report.json"
        if quality_src.exists() and quality_src.is_file():
            quality_local = self._copy_to_work_dir(quality_src, work_dir)
            converted["quality_report"] = str(quality_local)
            quality = manifest.get("quality")
            artifact_meta["quality_report"] = {
                "size_bytes": quality_src.stat().st_size,
                **(quality if isinstance(quality, dict) else {}),
            }

        if not converted:
            from backend.modules.warehouse.service.capture_finalize import (
                missing_artifacts_message,
                session_has_mapping_artifacts,
            )

            if not session_has_mapping_artifacts(session_dir):
                raise WarehouseScanMappingPreconditionError(missing_artifacts_message(session_dir))
            raise WarehouseScanMappingPreconditionError(
                "Warehouse capture did not produce a tileset, point cloud, or ROS artifact."
            )
        return converted, artifact_meta
