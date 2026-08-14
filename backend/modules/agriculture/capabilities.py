from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.capability_validation import (
    specialized_release_failures,
)
from backend.modules.agriculture.inference_profiles import (
    default_inference_profile as _default_inference_profile,
)
from backend.modules.agriculture.inference_profiles import (
    resolve_inference_profile,
)
from backend.modules.agriculture.models import AgricultureCapabilityRelease
from backend.modules.vision_models.contracts import VisionModelRelease
from backend.modules.vision_models.release_read_port import (
    list_production_model_releases,
)


@dataclass(frozen=True, slots=True)
class AgricultureCapability:
    id: str
    label: str
    description: str
    required_sensor: str = "rgb"
    required_media: str = "video"
    requires_model: bool = True
    output_type: str = "observations"
    action_relevance: str = "field_review"
    crop_specific: bool = False
    capture_conditions: dict[str, Any] | None = None
    evaluation_thresholds: dict[str, float] | None = None
    limitations: tuple[str, ...] = ()


CAPABILITIES: dict[str, AgricultureCapability] = {
    item.id: item
    for item in (
        AgricultureCapability(
            "quality",
            "Capture quality",
            "Checks blur, exposure, overlap, and whether the capture can be analyzed.",
            requires_model=False,
            output_type="quality_gate",
            action_relevance="reflight",
        ),
        AgricultureCapability(
            "coverage",
            "Field coverage",
            "Reports whether the planned field area has sufficient usable capture coverage.",
            requires_model=False,
            output_type="coverage_summary",
            action_relevance="reflight",
        ),
        AgricultureCapability(
            "object_detection",
            "Custom object detection",
            "Finds the crop-specific classes configured in the deployed Vision project.",
        ),
        AgricultureCapability(
            "stand_count",
            "Stand count",
            "Counts crop stands and seedlings from an evaluated detector.",
        ),
        AgricultureCapability(
            "weed_detection",
            "Weed detection",
            "Locates weed classes from an evaluated detector.",
        ),
        AgricultureCapability(
            "crop_health",
            "Crop-health findings",
            "Locates evaluated RGB visual crop-health classes for field review. "
            "Not calibrated NDVI or multispectral stress mapping.",
        ),
        AgricultureCapability(
            "canopy_cover",
            "Canopy cover",
            "Produces canopy findings from an evaluated model release.",
        ),
        AgricultureCapability(
            "row_detection",
            "Crop rows",
            "Finds crop-row structure from an evaluated model release.",
        ),
        AgricultureCapability(
            "standing_water",
            "Standing water",
            "Locates visible standing-water classes from an evaluated detector.",
        ),
        AgricultureCapability(
            "fruit_counting",
            "Crop-specific fruit counting",
            "Counts visible fruit with a released model scoped to one crop and "
            "documented capture conditions.",
            crop_specific=True,
            capture_conditions={
                "sensor": "rgb",
                "media": "video",
                "maximum_target_gsd_cm": 2.0,
                "allowed_camera_orientations": ["nadir", "oblique"],
                "camera_calibration_required": True,
                "tracking_required": True,
            },
            evaluation_thresholds={"map50": 0.45, "recall": 0.55, "per_class_map50": 0.35},
            limitations=(
                "Counts only visible fruit represented in the released crop-specific classes.",
                "Occlusion, canopy overlap, and repeat views can bias counts; "
                "track deduplication is required.",
                "The result is not a yield forecast.",
            ),
        ),
        AgricultureCapability(
            "ripeness_classification",
            "Crop-specific ripeness classification",
            "Classifies visible ripeness classes only for the released crop, "
            "calibrated camera, and validated capture scope.",
            crop_specific=True,
            capture_conditions={
                "sensor": "rgb",
                "media": "video",
                "maximum_target_gsd_cm": 1.0,
                "allowed_camera_orientations": ["nadir", "oblique"],
                "camera_calibration_required": True,
                "growth_stage_required": True,
            },
            evaluation_thresholds={
                "map50": 0.50,
                "precision": 0.60,
                "recall": 0.55,
                "per_class_map50": 0.45,
            },
            limitations=(
                "Applies only to visible classes in the released crop-specific holdout evaluation.",
                "Lighting, white balance, occlusion, and cultivar appearance "
                "can invalidate RGB colour cues.",
                "Never generalizes ripeness to an unlisted crop or arbitrary RGB capture.",
            ),
        ),
    )
}

RETIRED_CAPABILITY_IDS = {"canopy", "rows", "weed", "water", "visible_water"}


def default_inference_profile(capability_id: str) -> dict[str, Any]:
    return _default_inference_profile(capability_id)


def scope_key(*, org_id: int | None, user_id: int | None) -> str:
    if org_id is not None:
        return f"org:{org_id}"
    if user_id is None:
        raise ValueError("A user scope is required when no organization is present")
    return f"user:{user_id}"


def validate_capability_ids(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    unknown: list[str] = []
    retired: list[str] = []
    for raw in values:
        value = str(raw).strip().lower().replace("-", "_")
        if value in RETIRED_CAPABILITY_IDS:
            retired.append(value)
            continue
        if value not in CAPABILITIES:
            unknown.append(value)
            continue
        if value not in result:
            result.append(value)
    if retired:
        raise ValueError(
            "Retired analysis capability names are not accepted: " + ", ".join(sorted(set(retired)))
        )
    if unknown:
        raise ValueError("Unknown analysis capabilities: " + ", ".join(sorted(set(unknown))))
    return result


def _frozen_inference_profile(version: VisionModelRelease) -> dict[str, Any] | None:
    audits = version.evaluation_metrics.get("deployment_audit")
    if not isinstance(audits, list):
        return None
    for audit in reversed(audits):
        if not isinstance(audit, dict):
            continue
        contract = audit.get("inference_contract")
        if not isinstance(contract, dict):
            continue
        legacy_keys = (
            "confidence_threshold",
            "frame_stride_seconds",
            "small_object_mode",
            "tracking_enabled",
            "tracker_type",
        )
        canonical_keys = (
            "profile_id",
            "profile_version",
            "sample_fps",
            "image_size",
            "confidence_threshold",
            "batch_size",
            "sahi_enabled",
        )
        if all(key in contract for key in legacy_keys) or all(
            key in contract for key in canonical_keys
        ):
            return dict(contract)
    return None


class AgricultureCapabilityReleaseService:
    @staticmethod
    async def _lock_release_scope(
        db: AsyncSession,
        *,
        release_scope: str,
        capability_id: str,
    ) -> None:
        """Serialize first activation as well as replacement for one release scope."""
        get_bind = getattr(db, "get_bind", None)
        if get_bind is None:
            return
        bind = get_bind()
        if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
            return
        lock_key = f"agriculture-capability-release:{release_scope}:{capability_id}"
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0))))

    async def activate_for_model_version(
        self,
        db: AsyncSession,
        *,
        version: VisionModelRelease,
        org_id: int | None,
        user_id: int,
    ) -> AgricultureCapabilityRelease:
        capability_id = validate_capability_ids([version.capability_id])[0]
        capability = CAPABILITIES[capability_id]
        if not capability.requires_model:
            raise ValueError(f"{capability_id} is a built-in capability")
        if version.status != "production":
            raise ValueError("Only a production Vision model can back a capability release")
        if org_id is None:
            belongs_to_scope = (
                version.project_org_id is None and version.project_created_by_user_id == user_id
            )
        else:
            belongs_to_scope = version.project_org_id == org_id
        if not belongs_to_scope:
            raise ValueError("Vision model does not belong to this release scope")
        specialized_failures = specialized_release_failures(
            crop_specific=capability.crop_specific,
            evaluation_thresholds=capability.evaluation_thresholds or {},
            version=version,
        )
        if specialized_failures:
            raise ValueError("; ".join(specialized_failures))
        inference_profile = resolve_inference_profile(
            capability_id, _frozen_inference_profile(version)
        )
        if (capability.capture_conditions or {}).get("tracking_required") and not (
            inference_profile["tracking_enabled"]
        ):
            raise ValueError("This capability requires tracking-enabled inference")

        release_scope = scope_key(org_id=org_id, user_id=user_id)
        await self._lock_release_scope(
            db,
            release_scope=release_scope,
            capability_id=capability_id,
        )
        existing = await db.scalar(
            select(AgricultureCapabilityRelease)
            .where(
                AgricultureCapabilityRelease.scope_key == release_scope,
                AgricultureCapabilityRelease.capability_id == capability_id,
                AgricultureCapabilityRelease.status == "active",
            )
            .with_for_update()
        )
        if existing is not None and existing.vision_model_version_id == version.version_id:
            existing.sensor_type = capability.required_sensor
            existing.crop_types = [version.crop]
            existing.approved_by_user_id = user_id
            existing.inference_profile = inference_profile
            existing.thresholds = {
                "evaluation": dict(capability.evaluation_thresholds or {}),
                "confidence": existing.inference_profile["confidence_threshold"],
            }
            return existing
        if existing is not None:
            existing.status = "retired"
            existing.retired_at = datetime.now(UTC)

        release = AgricultureCapabilityRelease(
            scope_key=release_scope,
            org_id=org_id,
            created_by_user_id=user_id,
            approved_by_user_id=user_id,
            capability_id=capability_id,
            vision_model_version_id=version.version_id,
            status="active",
            sensor_type=capability.required_sensor,
            crop_types=[version.crop],
            inference_profile=inference_profile,
            thresholds={
                "evaluation": dict(capability.evaluation_thresholds or {}),
                "confidence": inference_profile["confidence_threshold"],
            },
        )
        db.add(release)
        await db.flush()
        return release

    async def retire_for_model_version(
        self, db: AsyncSession, *, vision_model_version_id: str
    ) -> None:
        await db.execute(
            update(AgricultureCapabilityRelease)
            .where(
                AgricultureCapabilityRelease.vision_model_version_id == vision_model_version_id,
                AgricultureCapabilityRelease.status == "active",
            )
            .values(status="retired", retired_at=datetime.now(UTC))
        )

    async def active_release_snapshots(
        self,
        db: AsyncSession,
        *,
        org_id: int | None,
        user_id: int | None,
        capability_ids: Iterable[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        release_scope = scope_key(org_id=org_id, user_id=user_id)
        stmt = select(AgricultureCapabilityRelease).where(
            AgricultureCapabilityRelease.scope_key == release_scope,
            AgricultureCapabilityRelease.status == "active",
        )
        ids = list(capability_ids or [])
        if ids:
            stmt = stmt.where(AgricultureCapabilityRelease.capability_id.in_(ids))
        releases = list((await db.scalars(stmt)).all())
        versions = await list_production_model_releases(
            db,
            version_ids=[release.vision_model_version_id for release in releases],
        )
        return {
            release.capability_id: {
                "release_id": release.id,
                "status": release.status,
                "capability_id": release.capability_id,
                "vision_model_version_id": version.version_id,
                "model_id": version.model_id,
                "model_name": version.model_name,
                "model_version": version.model_version,
                "model_checksum": version.model_checksum,
                "dataset_id": version.dataset_id,
                "crop": version.crop,
                "classes": list(version.classes),
                "evaluation_metrics": dict(version.evaluation_metrics),
                "sensor_type": release.sensor_type,
                "crop_types": list(release.crop_types or []),
                "inference_profile": resolve_inference_profile(
                    release.capability_id, release.inference_profile
                ),
                "thresholds": dict(release.thresholds or {}),
                "contract": {
                    "crop": version.crop,
                    "model_version_id": version.version_id,
                    "model_checksum": version.model_checksum,
                    "dataset_id": version.dataset_id,
                    "classes": list(version.classes),
                    "capture_conditions": dict(capability.capture_conditions or {}),
                    "evaluation_thresholds": dict(capability.evaluation_thresholds or {}),
                    "limitations": list(capability.limitations),
                    "crop_specific": capability.crop_specific,
                },
                "effective_from": (
                    release.effective_from.isoformat() if release.effective_from else None
                ),
            }
            for release in releases
            if (version := versions.get(release.vision_model_version_id)) is not None
            and (capability := CAPABILITIES.get(release.capability_id)) is not None
        }


agriculture_capability_release_service = AgricultureCapabilityReleaseService()
