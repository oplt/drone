from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.core.database.session import Session
from backend.modules.warehouse.models import WarehouseAsset
from backend.modules.warehouse.repository import WarehouseMappingRepository

logger = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WarehouseScanMappingError(RuntimeError):
    pass


_ARTIFACT_SUFFIXES = {
    ".db3",
    ".mcap",
    ".bag",
    ".ply",
    ".pcd",
    ".glb",
    ".json",
    ".bt",
    ".yaml",
    ".yml",
}
_SKIP_SUFFIXES = {".uploading", ".tmp", ".part"}


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _iter_artifact_files(session_dir: Path) -> Iterable[Path]:
    for path in session_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if any(name.endswith(suffix) for suffix in _SKIP_SUFFIXES):
            continue
        if path.suffix.lower() in _ARTIFACT_SUFFIXES or not path.suffix:
            yield path


def _collect_artifact_files(session_dir: Path) -> list[Path]:
    root = session_dir.resolve()
    files: list[Path] = []
    for path in _iter_artifact_files(root):
        resolved = path.resolve()
        if _is_within_root(resolved, root):
            files.append(resolved)
    return sorted(files, key=lambda p: str(p.relative_to(root)))


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

        resolved_session_dir = session_dir.expanduser().resolve()
        if not resolved_session_dir.exists() or not resolved_session_dir.is_dir():
            raise WarehouseScanMappingError(
                f"Capture session directory is missing: {resolved_session_dir}"
            )

        files = await asyncio.to_thread(_collect_artifact_files, resolved_session_dir)
        if not files:
            raise WarehouseScanMappingError(f"No mapping artifacts found in {resolved_session_dir}")

        repo = WarehouseMappingRepository()
        async with Session() as db:
            try:
                model, job = await repo.create_mapping_job(
                    db,
                    warehouse_map_id=int(warehouse_map_id),
                    capture_result=dict(capture_result),
                    reference_mapping_job_id=reference_mapping_job_id,
                    flight_id=flight_id,
                    input_source=input_source,
                )
                for file_path in files:
                    try:
                        relative_path = str(file_path.relative_to(resolved_session_dir))
                    except ValueError:
                        relative_path = file_path.name
                    stat = await asyncio.to_thread(file_path.stat)
                    checksum = await asyncio.to_thread(_sha256_file, file_path)
                    db.add(
                        WarehouseAsset(
                            model_id=model.id,
                            frame_id="odom",
                            type=_asset_type(file_path),
                            url=str(file_path),
                            size_bytes=stat.st_size,
                            checksum=checksum,
                            meta_data={
                                "job_id": job.id,
                                "artifact_key": file_path.suffix.lower().lstrip(".") or "file",
                                "relative_path": relative_path,
                                "capture_result": dict(capture_result),
                            },
                        )
                    )
                await repo.mark_job_ready(db, job=job, model=model)
                await db.commit()
                model_id = int(model.id)
                job_id = int(job.id)
            except Exception as exc:
                await db.rollback()
                logger.exception("warehouse_scan_mapping_persist_failed")
                raise WarehouseScanMappingError(str(exc)) from exc

        await _maybe_enqueue_structure_extraction(
            warehouse_map_id=int(warehouse_map_id),
            model_id=model_id,
            capture_result=capture_result,
        )

        return {
            "warehouse_map_id": int(warehouse_map_id),
            "model_id": model_id,
            "job_id": job_id,
            "artifact_count": len(files),
            "status": "ready",
        }


async def _maybe_enqueue_structure_extraction(
    *,
    warehouse_map_id: int,
    model_id: int,
    capture_result: dict[str, Any],
) -> None:
    """Enqueue post-flight structure extraction once a map becomes ready.

    Best-effort: a failure to enqueue must never fail map persistence (the
    operator can re-trigger extraction from the UI).
    """
    from backend.core.config.runtime import settings

    if not getattr(settings, "warehouse_structure_extraction_enabled", True):
        return
    client_flight_id = str(capture_result.get("client_flight_id") or "").strip()
    if not client_flight_id:
        logger.info(
            "warehouse_structure_extraction_skipped reason=no_client_flight_id map_id=%s",
            warehouse_map_id,
        )
        return
    try:
        from backend.modules.warehouse.service.structure_jobs import (
            create_durable_extraction_job,
            record_extraction_queued,
            update_durable_extraction_job,
            warehouse_mapping_worker_ready,
        )

        worker_ok, worker_detail = warehouse_mapping_worker_ready()
        if not worker_ok:
            logger.warning(
                "warehouse_structure_extraction_skipped "
                "reason=worker_unavailable map_id=%s detail=%s",
                warehouse_map_id,
                worker_detail,
            )
            return

        from backend.infrastructure.jobs import enqueue_task

        async with Session() as state_db:
            durable_job = await create_durable_extraction_job(
                state_db,
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                client_flight_id=client_flight_id,
                params={"capture_result": dict(capture_result)},
            )
            await state_db.commit()
        task_id = durable_job.processor_task_id
        if task_id is None:
            task_id = enqueue_task(
                "warehouse_mapping.extract_structure",
                queue=settings.celery_warehouse_mapping_queue,
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                client_flight_id=client_flight_id,
                extraction_job_id=int(durable_job.id),
            )
            async with Session() as state_db:
                await update_durable_extraction_job(
                    state_db,
                    warehouse_map_id=int(warehouse_map_id),
                    model_id=int(model_id),
                    status="queued",
                    task_id=task_id,
                    job_id=int(durable_job.id),
                )
                await state_db.commit()
        record_extraction_queued(
            warehouse_map_id=int(warehouse_map_id),
            model_id=int(model_id),
            client_flight_id=client_flight_id,
            task_id=task_id,
            source="persist_capture",
        )
        logger.info(
            "warehouse_structure_extraction_enqueued map_id=%s model_id=%s flight=%s",
            warehouse_map_id,
            model_id,
            client_flight_id,
        )
    except Exception:
        logger.warning(
            "warehouse_structure_extraction_enqueue_failed map_id=%s",
            warehouse_map_id,
            exc_info=True,
        )


def _asset_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".db3", ".mcap", ".bag"}:
        return "ROSBAG"
    if suffix in {".ply", ".pcd"}:
        return "POINT_CLOUD"
    if suffix == ".glb":
        return "MESH_GLB"
    if suffix in {".json", ".yaml", ".yml"}:
        return "QUALITY_REPORT"
    if suffix == ".bt":
        return "OCTOMAP"
    return "WAREHOUSE_ARTIFACT"
