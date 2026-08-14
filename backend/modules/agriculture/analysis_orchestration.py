from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.modules.agriculture.capabilities import (
    CAPABILITIES,
    agriculture_capability_release_service,
    validate_capability_ids,
)
from backend.modules.agriculture.inference_profiles import video_request_for_profile
from backend.modules.agriculture.models import (
    AgricultureAnalysisRun,
    AgricultureAnalysisStage,
    AgricultureAnalysisVideoJob,
    AgricultureFlight,
)
from backend.modules.identity.models import User
from backend.modules.video_analysis.contracts import VideoJobRef, video_analysis_port


class AgricultureAnalysisReadinessError(ValueError):
    def __init__(self, readiness: dict[str, Any], unavailable: list[str]) -> None:
        super().__init__("One or more requested analyses are not ready")
        self.readiness = readiness
        self.unavailable = unavailable


class AgricultureAnalysisOrchestration:
    async def readiness(
        self,
        db: AsyncSession,
        *,
        flight: AgricultureFlight,
        user: User,
    ) -> dict[str, Any]:
        sources = await video_analysis_port.list_mission_sources(
            db,
            mission_id=flight.mission_id,
            org_id=flight.org_id,
            user_id=user.id,
        )
        releases = await agriculture_capability_release_service.active_release_snapshots(
            db,
            org_id=flight.org_id,
            user_id=user.id,
        )
        profile = dict(flight.profile_snapshot or {})
        sensors = set(profile.get("sensor_inventory") or ["rgb"])
        crop = str(profile.get("crop_type") or "").strip().lower()
        capture_finalized = flight.status in {
            "captured",
            "processing",
            "review",
            "failed",
        }
        capture_prerequisites = [
            {
                "id": "capture_finalized",
                "label": "Capture finalized",
                "satisfied": capture_finalized,
                "message": (
                    "The flight recording is finalized."
                    if capture_finalized
                    else "Finish or finalize the flight before post-flight analysis."
                ),
            },
            {
                "id": "mission_video",
                "label": "Mission video available",
                "satisfied": bool(sources),
                "message": (
                    f"{len(sources)} mission video source(s) are available."
                    if sources
                    else "Upload or finalize at least one mission video."
                ),
            },
            {
                "id": "rgb_capture",
                "label": "RGB sensor recorded",
                "satisfied": "rgb" in sensors,
                "message": (
                    "RGB capture metadata is present."
                    if "rgb" in sensors
                    else "These post-flight analyses require RGB capture metadata."
                ),
            },
            {
                "id": "quality_target",
                "label": "Capture-quality target",
                "satisfied": profile.get("target_gsd_cm") is not None,
                "message": (
                    f"Target ground sampling distance: {profile['target_gsd_cm']} cm."
                    if profile.get("target_gsd_cm") is not None
                    else (
                        "No target ground sampling distance was recorded; "
                        "quality will be reported with reduced context."
                    )
                ),
            },
        ]
        capabilities: list[dict[str, Any]] = []
        for capability in CAPABILITIES.values():
            release = releases.get(capability.id)
            reasons: list[str] = []
            if not capture_finalized:
                reasons.append("Flight capture is not finalized.")
            if not sources:
                reasons.append("No mission video is available for analysis.")
            if capability.required_sensor not in sensors:
                reasons.append(f"Requires {capability.required_sensor.upper()} capture.")
            if capability.requires_model and release is None:
                reasons.append("No production Vision model is released for this capability.")
            if release is not None and crop and release.get("crop_types"):
                supported = {str(item).strip().lower() for item in release["crop_types"]}
                if crop not in supported:
                    reasons.append(
                        f"Released model is for {', '.join(sorted(supported))}, not {crop}."
                    )
            conditions = dict(capability.capture_conditions or {})
            if capability.crop_specific and not crop:
                reasons.append("A named crop is required for this crop-specific capability.")
            maximum_gsd = conditions.get("maximum_target_gsd_cm")
            if maximum_gsd is not None and (
                profile.get("target_gsd_cm") is None
                or float(profile["target_gsd_cm"]) > float(maximum_gsd)
            ):
                reasons.append(f"Requires target GSD at or below {maximum_gsd:g} cm/px.")
            allowed_orientations = set(conditions.get("allowed_camera_orientations") or [])
            if (
                allowed_orientations
                and profile.get("camera_orientation") not in allowed_orientations
            ):
                reasons.append("Camera orientation is outside the released capture contract.")
            if conditions.get("camera_calibration_required") and not profile.get("calibration_ids"):
                reasons.append("A registered camera calibration is required.")
            if conditions.get("growth_stage_required") and not profile.get("growth_stage"):
                reasons.append("Growth stage is required for this crop-specific classification.")
            available = not reasons
            capabilities.append(
                {
                    "id": capability.id,
                    "label": capability.label,
                    "description": capability.description,
                    "available": available,
                    "recommended": available and capability.id in {"quality", "coverage"},
                    "unavailable_reasons": reasons,
                    "required_sensor": capability.required_sensor,
                    "required_media": capability.required_media,
                    "requires_model": capability.requires_model,
                    "output_type": capability.output_type,
                    "action_relevance": capability.action_relevance,
                    "crop_specific": capability.crop_specific,
                    "capture_conditions": conditions,
                    "evaluation_thresholds": dict(capability.evaluation_thresholds or {}),
                    "limitations": list(capability.limitations),
                    "advanced_defaults": (
                        dict(release.get("inference_profile") or {}) if release is not None else {}
                    ),
                    "release": release,
                }
            )
        return {
            "catalog_version": "agriculture-capabilities.v2",
            "flight_id": flight.id,
            "mission_id": flight.mission_id,
            "ready": any(item["available"] for item in capabilities),
            "media_count": len(sources),
            "sensor_inventory": sorted(sensors),
            "capture_prerequisites": capture_prerequisites,
            "capabilities": capabilities,
        }

    async def resolve_request(
        self,
        db: AsyncSession,
        *,
        flight: AgricultureFlight,
        user: User,
        requested: list[object],
    ) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, Any]]:
        capability_ids = validate_capability_ids(requested)
        if not capability_ids:
            capability_ids = ["quality", "coverage"]
        readiness = await self.readiness(db, flight=flight, user=user)
        by_id = {item["id"]: item for item in readiness["capabilities"]}
        unavailable = [
            capability_id
            for capability_id in capability_ids
            if not by_id[capability_id]["available"]
        ]
        if unavailable:
            raise AgricultureAnalysisReadinessError(readiness, unavailable)
        releases = {
            capability_id: by_id[capability_id]["release"]
            for capability_id in capability_ids
            if by_id[capability_id]["release"] is not None
        }
        return capability_ids, releases, readiness

    async def ensure_video_jobs(
        self,
        db: AsyncSession,
        *,
        run: AgricultureAnalysisRun,
        flight: AgricultureFlight,
        user: User,
        force: bool = False,
    ) -> list[AgricultureAnalysisVideoJob]:
        model_snapshots = dict(run.model_versions or {})
        if not model_snapshots:
            return []
        sources = await video_analysis_port.list_mission_sources(
            db,
            mission_id=flight.mission_id,
            org_id=flight.org_id,
            user_id=user.id,
        )
        existing = list(
            (
                await db.scalars(
                    select(AgricultureAnalysisVideoJob).where(
                        AgricultureAnalysisVideoJob.run_id == run.id
                    )
                )
            ).all()
        )
        if force and existing:
            await video_analysis_port.cancel_jobs(
                db,
                job_ids=[item.video_job_id for item in existing],
                user=user,
            )
            await db.execute(
                delete(AgricultureAnalysisVideoJob).where(
                    AgricultureAnalysisVideoJob.run_id == run.id
                )
            )
            await db.flush()
            existing = []
        existing_by_key = {(item.capability_id, item.video_id): item for item in existing}
        reusable_by_key: dict[tuple[str, str], tuple[VideoJobRef, AgricultureAnalysisVideoJob]] = {}
        if not force and sources and model_snapshots:
            release_ids = {str(snapshot["release_id"]) for snapshot in model_snapshots.values()}
            candidates = list(
                (
                    await db.scalars(
                        select(AgricultureAnalysisVideoJob)
                        .where(
                            AgricultureAnalysisVideoJob.run_id != run.id,
                            AgricultureAnalysisVideoJob.video_id.in_(
                                [source.id for source in sources]
                            ),
                            AgricultureAnalysisVideoJob.capability_id.in_(list(model_snapshots)),
                            AgricultureAnalysisVideoJob.capability_release_id.in_(release_ids),
                        )
                        .order_by(AgricultureAnalysisVideoJob.created_at.desc())
                        .limit(500)
                    )
                ).all()
            )
            candidate_jobs = await video_analysis_port.list_jobs(
                db,
                job_ids=sorted({item.video_job_id for item in candidates}),
                org_id=flight.org_id,
                user_id=user.id,
            )
            jobs_by_id = {job.id: job for job in candidate_jobs}
            for candidate in candidates:
                key = (candidate.capability_id, candidate.video_id)
                if key in reusable_by_key:
                    continue
                expected = dict(model_snapshots[candidate.capability_id])
                frozen = dict(candidate.inference_snapshot or {})
                job = jobs_by_id.get(candidate.video_job_id)
                expected_model = (
                    f"registered:{expected['vision_model_version_id']}:{expected['model_checksum']}"
                )
                if (
                    job is not None
                    and job.status == "completed"
                    and bool(job.source_checksum)
                    and job.source_checksum == frozen.get("source_checksum")
                    and job.model_version_id == expected["vision_model_version_id"]
                    and job.model_version == expected_model
                    and frozen.get("vision_model_version_id") == expected["vision_model_version_id"]
                    and frozen.get("model_checksum") == expected["model_checksum"]
                    and dict(job.inference_profile or {}) == expected.get("inference_profile", {})
                    and frozen.get("inference_profile", {}) == expected.get("inference_profile", {})
                    and frozen.get("telemetry_match_version") == "nearest-telemetry.v1"
                    and frozen.get("capability_contract_version") == "agriculture-capabilities.v1"
                ):
                    reusable_by_key[key] = (job, candidate)
        for capability_id, snapshot in model_snapshots.items():
            profile = dict(snapshot.get("inference_profile") or {})
            request = video_request_for_profile(
                capability_id=capability_id,
                model_version_id=snapshot["vision_model_version_id"],
                profile=profile,
            )
            assert request.inference_profile is not None
            profile = request.inference_profile.model_dump()
            profile_hash = profile["profile_digest"][:20]
            for source in sources:
                key = (capability_id, source.id)
                if key in existing_by_key:
                    continue
                reused = reusable_by_key.get(key)
                if reused is not None:
                    job, reused_link = reused
                else:
                    orchestration_key = (
                        f"agri:{run.id}:{source.id}:"
                        f"{snapshot['vision_model_version_id']}:{profile_hash}:a{run.retry_count}"
                    )
                    job = await video_analysis_port.start_or_reuse_job(
                        db,
                        video_id=source.id,
                        request=request,
                        user=user,
                        orchestration_key=orchestration_key,
                    )
                    reused_link = None
                link = AgricultureAnalysisVideoJob(
                    run_id=run.id,
                    capability_id=capability_id,
                    capability_release_id=snapshot["release_id"],
                    video_id=source.id,
                    video_job_id=job.id,
                    inference_snapshot={
                        **snapshot,
                        "inference_profile": profile,
                        "source_video_id": source.id,
                        "source_status_at_submission": source.status,
                        "video_job_id": job.id,
                        "submitted_at": datetime.now(UTC).isoformat(),
                        "capability_contract_version": "agriculture-capabilities.v1",
                        "telemetry_match_version": "nearest-telemetry.v1",
                        "aggregation_version": "agriculture-aggregation.v1",
                        "reused_completed_job": reused_link is not None,
                        "reused_from_run_id": (
                            reused_link.run_id if reused_link is not None else None
                        ),
                    },
                )
                db.add(link)
                existing.append(link)
                existing_by_key[key] = link
        stage = await self._video_stage(db, run.id)
        stage.status = "queued" if existing else "completed"
        stage.progress = 0.0 if existing else 100.0
        stage.metrics = {"job_count": len({item.video_job_id for item in existing})}
        await db.commit()
        return existing

    async def prerequisite_state(
        self,
        db: AsyncSession,
        *,
        run: AgricultureAnalysisRun,
        flight: AgricultureFlight,
    ) -> tuple[str, list[str]]:
        links = list(
            (
                await db.scalars(
                    select(AgricultureAnalysisVideoJob).where(
                        AgricultureAnalysisVideoJob.run_id == run.id
                    )
                )
            ).all()
        )
        if not run.model_versions:
            return "completed", []
        if not links:
            stage = await self._video_stage(db, run.id)
            stage.status = "failed"
            stage.finished_at = datetime.now(UTC)
            stage.error = "Required video inference jobs were not linked to this run."
            run.status = "failed"
            run.error = stage.error
            run.finished_at = stage.finished_at
            await db.commit()
            return "failed", []
        job_ids = sorted({item.video_job_id for item in links})
        jobs = await video_analysis_port.list_jobs(
            db,
            job_ids=job_ids,
            org_id=flight.org_id,
            user_id=run.requested_by_user_id,
        )
        by_id = {job.id: job for job in jobs}
        stage = await self._video_stage(db, run.id)
        missing = sorted(set(job_ids) - set(by_id))
        failed = [job for job in jobs if job.status in {"failed", "cancelled"}]
        completed = [job for job in jobs if job.status == "completed"]
        if missing or failed:
            stage.status = "failed"
            stage.finished_at = datetime.now(UTC)
            stage.error = "Required video inference failed or became unavailable."
            stage.metrics = {
                "job_count": len(job_ids),
                "failed_job_ids": [job.id for job in failed],
                "missing_job_ids": missing,
                "terminal_reasons": {job.id: job.terminal_reason_code for job in failed},
            }
            run.status = "failed"
            run.error = stage.error
            run.finished_at = datetime.now(UTC)
            await db.commit()
            return "failed", job_ids
        if len(completed) != len(job_ids):
            now = datetime.now(UTC)
            wait_started_raw = (run.audit_json or {}).get("inference_wait_started_at")
            if wait_started_raw:
                wait_started = datetime.fromisoformat(str(wait_started_raw))
                if wait_started.tzinfo is None:
                    wait_started = wait_started.replace(tzinfo=UTC)
            else:
                wait_started = now
                run.audit_json = {
                    **(run.audit_json or {}),
                    "inference_wait_started_at": now.isoformat(),
                }
            if now - wait_started >= timedelta(
                seconds=settings.agriculture_inference_wait_timeout_seconds
            ):
                stage.status = "failed"
                stage.finished_at = now
                stage.error = "Required video inference exceeded the allowed wait time."
                stage.metrics = {
                    "job_count": len(job_ids),
                    "completed_job_count": len(completed),
                    "job_statuses": {job.id: job.status for job in jobs},
                    "wait_started_at": wait_started.isoformat(),
                    "terminal_reason_code": "VIDEO_INFERENCE_WAIT_TIMEOUT",
                }
                run.status = "failed"
                run.error = stage.error
                run.finished_at = now
                await db.commit()
                return "failed", job_ids
            stage.status = "running"
            stage.started_at = stage.started_at or now
            stage.progress = len(completed) / len(job_ids) * 100.0 if job_ids else 100.0
            stage.metrics = {
                "job_count": len(job_ids),
                "completed_job_count": len(completed),
                "job_statuses": {job.id: job.status for job in jobs},
                "wait_started_at": wait_started.isoformat(),
            }
            run.status = "waiting_inference"
            run.progress = max(run.progress, 10.0)
            await db.commit()
            return "waiting", job_ids

        stage.status = "completed"
        stage.progress = 100.0
        stage.finished_at = datetime.now(UTC)
        stage.error = None
        stage.metrics = {
            "job_count": len(job_ids),
            "completed_job_count": len(completed),
            "source_checksums": {job.id: job.source_checksum for job in completed},
            "model_versions": {job.id: job.model_version for job in completed},
        }
        for link in links:
            job = by_id[link.video_job_id]
            link.inference_snapshot = {
                **(link.inference_snapshot or {}),
                "source_checksum": job.source_checksum,
                "resolved_model_version": job.model_version,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        await db.commit()
        return "completed", job_ids

    @staticmethod
    async def _video_stage(db: AsyncSession, run_id: str) -> AgricultureAnalysisStage:
        stage = await db.scalar(
            select(AgricultureAnalysisStage).where(
                AgricultureAnalysisStage.run_id == run_id,
                AgricultureAnalysisStage.stage_name == "video_inference",
            )
        )
        if stage is None:
            stage = AgricultureAnalysisStage(run_id=run_id, stage_name="video_inference")
            db.add(stage)
            await db.flush()
        return stage


agriculture_analysis_orchestration = AgricultureAnalysisOrchestration()
