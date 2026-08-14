"""Structure job module."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.infrastructure.cache.local import BoundedTTLCache
from backend.infrastructure.cache.redis import get_sync_redis_client, redis_available
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseCoordinateFrame,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    record_inspection_target_clearance_failure,
    record_low_confidence_candidate,
    record_structure_extraction_failure,
)
from backend.modules.warehouse.schemas import WarehouseLocalPose, WarehouseSensorAim
from backend.modules.warehouse.service.drift_guard import (
    transform_checksum,
    validate_localization_evidence,
)
from backend.modules.warehouse.service.gazebo_landmark_consistency import (
    LandmarkObservation,
    LandmarkSpec,
    evaluate_landmark_consistency,
)
from backend.modules.warehouse.service.layout import create_extracted_layout
from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest
from backend.modules.warehouse.service.live_map_readiness import (
    refresh_structure_input_readiness,
)
from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage,
)
from backend.modules.warehouse.service.occupancy_grid_parser import (
    occupancy_grid_from_ros_yaml,
)
from backend.modules.warehouse.service.scan_to_layout import (
    CandidateInput,
    extraction_confidence,
    persist_candidates,
)
from backend.modules.warehouse.service.structure_extraction import (
    StructureExtractionParams,
    StructureResult,
    extract_structure_from_flight,
)
from backend.observability.profiling import profile_stage

logger = logging.getLogger(__name__)

from .artifacts import _debug_payload, _scan_artifact_lineage, _write_debug_artifact, _write_summary_asset, _safe_debug_value
from .constants import STRUCTURE_ASSET_TYPE, STRUCTURE_DEBUG_ASSET_TYPE, STRUCTURE_EXTRACTION_ALGORITHM_VERSION
from .failure_codes import _quality_failure_reason_codes

async def _persist_result(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    result: StructureResult,
    coordinate_frame_id: int,
) -> dict[str, Any]:
    quality = result.summary.get("quality") if isinstance(result.summary, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    quality_status = str(quality.get("status") or "ready")
    active_target_count = sum(target.clearance_status == "active" for target in result.targets)
    review_target_count = sum(
        target.clearance_status == "needs_review" for target in result.targets
    )
    rejected_target_count = sum(target.clearance_status == "rejected" for target in result.targets)
    extraction_params = dict(result.summary.get("params") or {})
    lineage_checksum, manifest_json, inputs_json = await asyncio.to_thread(
        _scan_artifact_lineage,
        client_flight_id,
        model_id=int(model_id),
        coordinate_frame_id=int(coordinate_frame_id),
        extraction_params=extraction_params,
    )
    failure_reason_codes = _quality_failure_reason_codes(result.summary)
    summary_path = await asyncio.to_thread(
        _write_summary_asset, client_flight_id, result.summary, lineage_checksum
    )
    debug_payload = _debug_payload(
        warehouse_map_id=warehouse_map_id,
        model_id=model_id,
        client_flight_id=client_flight_id,
        coordinate_frame_id=coordinate_frame_id,
        result=result,
        lineage_checksum=lineage_checksum,
        manifest_json=manifest_json,
        inputs_json=inputs_json,
        failure_reason_codes=failure_reason_codes,
    )
    debug_path, debug_url = await asyncio.to_thread(
        _write_debug_artifact,
        client_flight_id,
        payload=debug_payload,
        lineage_checksum=lineage_checksum,
    )

    async with Session() as db:
        try:
            model = await db.get(WarehouseModel, int(model_id))
            if model is None:
                raise RuntimeError(f"Warehouse model {model_id} was not found")
            model.coordinate_frame_id = int(coordinate_frame_id)
            warehouse_map = await db.get(WarehouseMap, int(warehouse_map_id))
            if warehouse_map is None:
                raise RuntimeError(f"Warehouse map {warehouse_map_id} was not found")
            rig_scope = (
                WarehouseSensorRig.org_id == warehouse_map.org_id
                if warehouse_map.org_id is not None
                else and_(
                    WarehouseSensorRig.org_id.is_(None),
                    WarehouseSensorRig.owner_id == warehouse_map.owner_id,
                )
            )
            sensor_rig = (
                await db.execute(
                    select(WarehouseSensorRig)
                    .where(
                        WarehouseSensorRig.active.is_(True),
                        WarehouseSensorRig.calibration_status == "valid",
                        WarehouseSensorRig.calibration_hash.is_not(None),
                        rig_scope,
                    )
                    .order_by(WarehouseSensorRig.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            artifact_set = (
                await db.execute(
                    select(WarehouseScanArtifactSet).where(
                        WarehouseScanArtifactSet.checksum_sha256 == lineage_checksum
                    )
                )
            ).scalar_one_or_none()
            if artifact_set is None:
                artifact_set = WarehouseScanArtifactSet(
                    warehouse_map_id=int(warehouse_map_id),
                    map_model_id=int(model_id),
                    coordinate_frame_id=int(coordinate_frame_id),
                    sensor_rig_id=int(sensor_rig.id) if sensor_rig is not None else None,
                    calibration_hash=(
                        sensor_rig.calibration_hash if sensor_rig is not None else None
                    ),
                    client_flight_id=client_flight_id,
                    checksum_sha256=lineage_checksum,
                    manifest_json=manifest_json,
                    inputs_json=inputs_json,
                    extraction_params_json=extraction_params,
                    algorithm_version=STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                )
                db.add(artifact_set)
                await db.flush()
            layout, bin_ids, published = await create_extracted_layout(
                db,
                warehouse_map_id=int(warehouse_map_id),
                coordinate_frame_id=int(coordinate_frame_id),
                map_model_id=int(model_id),
                artifact_set_id=int(artifact_set.id),
                input_checksum=lineage_checksum,
                algorithm_version=STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                targets=result.targets,
            )
            await persist_candidates(
                db,
                warehouse_map_id=int(warehouse_map_id),
                layout_version_id=int(layout.id),
                candidates=[
                    CandidateInput(
                        entity_kind="bin",
                        identity_key=(
                            f"{target.aisle_code}/{target.rack_code}/"
                            f"{target.shelf_level}/{target.bin_code}"
                        ),
                        geometry={"target_point": target.target_point},
                        confidence=extraction_confidence(target),
                    )
                    for target in result.targets
                ],
            )
            # Idempotent re-run: drop the previous auto-generated targets for this
            # model (identified by reference_model_id) while leaving operator-made
            # targets (reference_model_id NULL or other models) untouched.
            await db.execute(
                delete(WarehouseScanTarget).where(
                    WarehouseScanTarget.warehouse_map_id == int(warehouse_map_id),
                    WarehouseScanTarget.reference_model_id == int(model_id),
                    WarehouseScanTarget.provenance_status == "auto",
                )
            )

            for tgt in result.targets:
                scan_pose = WarehouseLocalPose.model_validate(tgt.scan_pose).model_dump()
                scan_pose["_clearance_status"] = tgt.clearance_status
                scan_pose["_clearance_m"] = tgt.clearance_m
                scan_pose["_clearance_source"] = tgt.clearance_source
                db.add(
                    WarehouseScanTarget(
                        warehouse_map_id=int(warehouse_map_id),
                        reference_model_id=int(model_id),
                        coordinate_frame_id=int(coordinate_frame_id),
                        layout_version_id=int(layout.id),
                        bin_id=bin_ids[
                            (
                                str(tgt.aisle_code),
                                str(tgt.rack_code),
                                int(tgt.shelf_level),
                                str(tgt.bin_code),
                            )
                        ],
                        aisle_code=tgt.aisle_code,
                        rack_code=tgt.rack_code,
                        shelf_level=tgt.shelf_level,
                        bin_code=tgt.bin_code,
                        target_point_local_json=tgt.target_point,
                        scan_pose_local_json=scan_pose,
                        sensor_aim_json=WarehouseSensorAim(
                            aim_point_local_json=tgt.target_point,
                            orientation=scan_pose["orientation"],
                        ).model_dump(),
                        shelf_normal_local_json=tgt.shelf_normal,
                        scanner_metadata_json=dict(tgt.scanner_metadata or {}),
                        path_validation_json=dict(tgt.path_validation or {}),
                        failure_reason=tgt.failure_reason,
                        standoff_m=float(tgt.standoff_m),
                        priority=int(tgt.priority),
                        active=(
                            published
                            and tgt.clearance_status == "active"
                            and tgt.failure_reason is None
                        ),
                        provenance_status="auto",
                    )
                )

            db.add(
                WarehouseAsset(
                    model_id=int(model_id),
                    coordinate_frame_id=int(coordinate_frame_id),
                    frame_id="warehouse_map",
                    type=STRUCTURE_ASSET_TYPE,
                    url=str(summary_path) if summary_path else f"memory://structure/{model_id}",
                    checksum=hashlib.sha256(
                        json.dumps(result.summary, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    meta_data={
                        "warehouse_map_id": int(warehouse_map_id),
                        "coordinate_frame_id": int(coordinate_frame_id),
                        "artifact_set_id": int(artifact_set.id),
                        "input_checksum": lineage_checksum,
                        "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                        "layout_version_id": int(layout.id),
                        "layout_published": published,
                        "client_flight_id": client_flight_id,
                        "generated_at": datetime.now(UTC).isoformat(),
                        "summary": result.summary,
                        "target_count": len(result.targets),
                        "active_target_count": active_target_count,
                        "review_target_count": review_target_count,
                        "rejected_target_count": rejected_target_count,
                        "coordinate_setup_status": (
                            "active" if active_target_count > 0 else "draft"
                        ),
                        "manual_review_required": quality_status != "ready"
                        or review_target_count > 0,
                        "quality_status": quality_status,
                        "quality_reasons": list(quality.get("reasons") or []),
                        "failure_reason_codes": failure_reason_codes,
                        "confidence": quality.get("confidence"),
                        "debug_artifact_url": debug_url,
                        "debug_artifact_path": str(debug_path) if debug_path else None,
                    },
                )
            )
            if debug_path is not None:
                db.add(
                    WarehouseAsset(
                        model_id=int(model_id),
                        coordinate_frame_id=int(coordinate_frame_id),
                        frame_id="warehouse_map",
                        type=STRUCTURE_DEBUG_ASSET_TYPE,
                        url=debug_url or str(debug_path),
                        checksum=hashlib.sha256(
                            json.dumps(
                                debug_payload,
                                sort_keys=True,
                                separators=(",", ":"),
                                default=_safe_debug_value,
                            ).encode()
                        ).hexdigest(),
                        meta_data={
                            "warehouse_map_id": int(warehouse_map_id),
                            "coordinate_frame_id": int(coordinate_frame_id),
                            "artifact_set_id": int(artifact_set.id),
                            "input_checksum": lineage_checksum,
                            "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                            "client_flight_id": client_flight_id,
                            "failure_reason_codes": failure_reason_codes,
                            "quality_status": quality_status,
                            "path": str(debug_path),
                        },
                    )
                )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("structure_extraction: persistence failed")
            raise RuntimeError(str(exc)) from exc

    return {
        "warehouse_map_id": int(warehouse_map_id),
        "model_id": int(model_id),
        "client_flight_id": client_flight_id,
        "target_count": len(result.targets),
        "active_target_count": active_target_count,
        "review_target_count": review_target_count,
        "rejected_target_count": rejected_target_count,
        "coordinate_setup_status": "active" if active_target_count > 0 else "draft",
        "manual_review_required": quality_status != "ready" or review_target_count > 0,
        "rejected_clearance": result.rejected_clearance,
        "aisles": int(result.summary.get("counts", {}).get("aisles", 0)),
        "racks": int(result.summary.get("counts", {}).get("racks", 0)),
        "status": quality_status,
        "artifact_set_checksum": lineage_checksum,
        "layout_version_id": int(layout.id),
        "layout_published": published,
        "quality_status": quality_status,
        "quality_reasons": list(quality.get("reasons") or []),
        "failure_reason_codes": failure_reason_codes,
        "debug_artifact_url": debug_url,
        "confidence": quality.get("confidence"),
    }
