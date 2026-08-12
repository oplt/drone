from __future__ import annotations

import hashlib
import logging
import shutil
import time
from collections.abc import AsyncIterator
from pathlib import Path

import cv2
from numpy.typing import NDArray
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.agriculture.ports.telemetry import (
    list_mission_telemetry_for_georef,
)
from backend.modules.video_analysis.models import (
    StorageObject,
    VideoDetection,
    new_uuid,
)
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.service.detector import create_frame_detector
from backend.modules.video_analysis.service.frame_extractor import (
    async_iter_frames,
    read_video_metadata_async,
)
from backend.modules.video_analysis.service.geo import NearestTelemetryMatcher
from backend.modules.video_analysis.service.tracker import FrameTracker
from backend.modules.vision_models.application import VisionApplication
from backend.modules.vision_models.config import vision_settings
from backend.observability import prometheus_metrics
from backend.observability.instruments import observed_span, structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

logger = logging.getLogger(__name__)
MAX_PENDING_DETECTIONS = 100


class VideoAnalysisCancelled(RuntimeError):
    pass


class OfflineVideoAnalysisPipeline:
    def __init__(
        self, db: AsyncSession, *, evidence_root: str | Path = "backend/storage/video_analysis"
    ):
        self.db = db
        self.repo = VideoAnalysisRepository(db)
        self.evidence_root = Path(evidence_root)

    async def run(self, job_id: str) -> None:
        job = await self.repo.get_job(job_id)
        if job is None:
            raise ValueError(f"VideoAnalysisJob not found: {job_id}")
        if job.status == "completed":
            return

        video = await self.repo.get_video(job.video_id)
        if video is None:
            raise ValueError(f"VideoAsset not found: {job.video_id}")

        claimed_attempt = await self.repo.mark_job_running(job)
        if claimed_attempt is None:
            return
        await run_blocking(
            self._clear_prior_evidence,
            job.id,
            boundary="filesystem",
            operation="clear_video_evidence",
            timeout_s=30.0,
        )
        frames_received = 0
        frames_decoded = 0
        frames_attempted = 0
        frames_processed = 0
        frames_persisted = 0
        frames_dropped = 0
        frames_failed = 0
        total_inference_latency_ms = 0.0
        pipeline_started = time.monotonic()
        job_created_at = getattr(job, "created_at", None)
        queue_wait_ms = (
            max(
                0.0,
                (
                    (getattr(job, "started_at", None) or video.created_at)
                    - job_created_at
                ).total_seconds()
                * 1000.0,
            )
            if job_created_at is not None
            else 0.0
        )
        stage_timings = {
            "queue_wait": queue_wait_ms,
            "decode": 0.0,
            "inference": 0.0,
            "tracking": 0.0,
            "telemetry": 0.0,
            "crop": 0.0,
            "persist": 0.0,
            "summary": 0.0,
            "total": 0.0,
        }
        failure_stage = "source_validation"

        try:
            video_path = Path(video.storage_path)
            source_checksum = await run_blocking(
                self._sha256_file,
                video_path,
                boundary="filesystem",
                operation="hash_video_source",
                timeout_s=120.0,
            )
            await self.repo.set_source_checksum(job, source_checksum)
            failure_stage = "video_decode"
            decode_started = time.monotonic()
            with observed_span(
                "video.metadata",
                mission_id=video.mission_id,
                camera_name="offline_video",
                **{"model.name": job.model_name},
            ):
                metadata = await read_video_metadata_async(video_path)
            stage_timings["decode"] += (time.monotonic() - decode_started) * 1000.0
            logger.info(
                "Processing video analysis job_id=%s video_id=%s "
                "duration_seconds=%.2f stride_seconds=%.2f model=%s",
                job.id,
                video.id,
                metadata.duration_seconds,
                job.frame_stride_seconds,
                job.model_name,
            )
            await self.repo.update_video_metadata(
                video,
                fps=metadata.fps,
                width=metadata.width,
                height=metadata.height,
                duration_seconds=metadata.duration_seconds,
                status="analyzing",
            )

            registered_version = None
            registered_path = None
            failure_stage = "model_loading"
            if job.model_version_id:
                (
                    registered_path,
                    registered_version,
                ) = await VisionApplication().resolve_registered_weights(
                    self.db,
                    job.model_version_id,
                    org_id=job.org_id,
                    user_id=video.uploaded_by_user_id,
                    require_production=False,
                )
            detector = await run_blocking(
                create_frame_detector,
                model_name=job.model_name,
                confidence_threshold=job.confidence_threshold,
                model_path=registered_path,
                small_object_mode=job.small_object_mode,
                expected_checksum=(
                    registered_version.checksum
                    if registered_version is not None
                    else None
                ),
                boundary="media",
                operation="load_detector",
                timeout_s=120.0,
            )
            resolved_version = (
                f"registered:{registered_version.id}:{registered_version.checksum}"
                if registered_version is not None
                else detector.model_version
            )
            await self.repo.set_model_version(job, resolved_version)
            loaded_model_hash = getattr(detector, "loaded_model_hash", detector.model_version)
            loaded_hash_setter = getattr(self.repo, "set_loaded_model_hash", None)
            if loaded_hash_setter is not None:
                await loaded_hash_setter(job, loaded_model_hash)
            telemetry_samples = (
                await list_mission_telemetry_for_georef(
                    self.db, mission_id=video.mission_id
                )
                if video.mission_id
                else []
            )
            if getattr(video, "captured_at", None) is None and getattr(
                video, "capture_time_source", "unknown"
            ) in {
                "unknown",
                "upload_time",
            }:
                video.capture_time_source = "upload_time"
            capture_base = getattr(video, "captured_at", None) or video.created_at
            if getattr(video, "sync_offset_seconds", 0.0):
                from datetime import timedelta

                capture_base += timedelta(seconds=video.sync_offset_seconds)
            telemetry = NearestTelemetryMatcher(
                video.mission_id, telemetry_samples, capture_base
            )
            tracker = (
                FrameTracker(sampled_frame_rate=1.0 / max(job.frame_stride_seconds, 0.1))
                if job.tracking_enabled
                else None
            )
            if tracker is not None:
                logger.info(
                    "tracking_initialized tracker=%s sampled_frame_rate=%.3f",
                    job.tracker_type,
                    tracker.sampled_frame_rate,
                )
            if job.small_object_mode:
                logger.info(
                    "sahi_enabled slice=%dx%d overlap=%.2f",
                    vision_settings.video_sahi_slice_width,
                    vision_settings.video_sahi_slice_height,
                    vision_settings.video_sahi_overlap_width_ratio,
                )

            pending_detections: list[VideoDetection] = []
            detection_count = 0
            estimated_total = max(
                1,
                int(metadata.duration_seconds / max(job.frame_stride_seconds, 0.1)),
            )

            processed = 0
            failure_stage = "inference"
            async for (
                frame,
                prefetched_detections,
                prefetch_error,
                prefetched_latency_ms,
            ) in self._iter_inference_frames(
                video_path,
                every_seconds=job.frame_stride_seconds,
                decode_stride_enabled=settings.video_analysis_decode_stride_enabled,
                detector=detector,
                allow_batching=not job.small_object_mode and not job.tracking_enabled,
            ):
                processed += 1
                frames_attempted += 1
                if processed % 20 == 0 and await self.repo.is_job_cancelled(job.id):
                    raise VideoAnalysisCancelled("Video analysis was cancelled.")
                frames_received += 1
                frames_decoded += 1
                metric_add("video_frames_received", attrs={"source": "offline_video"})
                inference_started = time.monotonic()
                with observed_span(
                    "video.inference",
                    mission_id=video.mission_id,
                    frame_id=frame.frame_index,
                    camera_name="offline_video",
                    **{
                        "model.name": job.model_name,
                        "video.width": metadata.width,
                        "video.height": metadata.height,
                        "video.fps": metadata.fps,
                    },
                ) as span:
                    try:
                        detection_started = time.monotonic()
                        if prefetch_error is not None:
                            raise prefetch_error
                        if prefetched_detections is None:
                            frame_detections = await run_blocking(
                                detector.predict,
                                frame.image_bgr,
                                boundary="cpu",
                                operation="video_inference",
                                timeout_s=120.0,
                            )
                            detection_latency_ms = (
                                time.monotonic() - detection_started
                            ) * 1000.0
                        else:
                            frame_detections = prefetched_detections
                            detection_latency_ms = prefetched_latency_ms
                        stage_timings["inference"] += detection_latency_ms
                        metric_record(
                            "video_sahi_inference_latency"
                            if job.small_object_mode
                            else "video_standard_inference_latency",
                            detection_latency_ms,
                            {"model": job.model_name},
                        )
                        if tracker is not None:
                            tracking_started = time.monotonic()
                            frame_detections = await run_blocking(
                                tracker.update,
                                frame_detections,
                                boundary="cpu",
                                operation="video_tracking",
                                timeout_s=30.0,
                            )
                            metric_record(
                                "video_tracking_latency",
                                (time.monotonic() - tracking_started) * 1000.0,
                                {"tracker": job.tracker_type},
                            )
                            stage_timings["tracking"] += (
                                time.monotonic() - tracking_started
                            ) * 1000.0
                            metric_record(
                                "video_track_count",
                                sum(item.track_id is not None for item in frame_detections),
                                {"tracker": job.tracker_type},
                            )
                    except Exception as exc:
                        frames_failed += 1
                        total_inference_latency_ms += (
                            time.monotonic() - inference_started
                        ) * 1000.0
                        logger.exception(
                            "Video frame inference failed job_id=%s frame_index=%s",
                            job.id,
                            frame.frame_index,
                        )
                        if job.small_object_mode:
                            raise RuntimeError(
                                "Small-object analysis failed. Check worker logs for details."
                            ) from exc
                        if not await self.repo.heartbeat(
                            job, expected_attempt=claimed_attempt
                        ):
                            return
                        continue
                    inference_latency_ms = (
                        prefetched_latency_ms
                        if prefetched_detections is not None
                        else (time.monotonic() - inference_started) * 1000.0
                    )
                    total_inference_latency_ms += inference_latency_ms
                    if span is not None:
                        span.set_attribute("detection.count", len(frame_detections))
                        span.set_attribute("inference.latency_ms", inference_latency_ms)
                    metric_record(
                        "video_inference_latency",
                        inference_latency_ms,
                        {"model": job.model_name},
                    )
                    metric_record(
                        "video_detection_count",
                        len(frame_detections),
                        {"model": job.model_name},
                    )
                metric_add("video_frames_processed", attrs={"source": "offline_video"})
                frames_processed += 1
                frames_persisted += 1
                if not await self.repo.heartbeat(
                    job, expected_attempt=claimed_attempt
                ):
                    return
                telemetry_started = time.monotonic()
                geo = telemetry.match(frame.timestamp_seconds)
                stage_timings["telemetry"] += (
                    time.monotonic() - telemetry_started
                ) * 1000.0

                for idx, det in enumerate(frame_detections):
                    detection_count += 1
                    with observed_span(
                        "video.detection_storage",
                        mission_id=video.mission_id,
                        frame_id=frame.frame_index,
                        camera_name="offline_video",
                        **{
                            "model.name": job.model_name,
                            "detection.count": len(frame_detections),
                        },
                    ):
                        detection_id = new_uuid()
                        storage_object = None
                        save_crop = self.should_store_crop(
                            confidence=det.confidence,
                            track_id=det.track_id,
                        )
                        if save_crop:
                            crop_started = time.monotonic()
                            crop_result = await run_blocking(
                                self._save_crop,
                                job_id=job.id,
                                frame_index=frame.frame_index,
                                detection_index=idx,
                                image_bgr=frame.image_bgr,
                                xyxy=(det.x1, det.y1, det.x2, det.y2),
                                boundary="media",
                                operation="save_detection_crop",
                                timeout_s=30.0,
                            )
                            stage_timings["crop"] += (
                                time.monotonic() - crop_started
                            ) * 1000.0
                            if crop_result is not None:
                                crop_path, checksum, size = crop_result
                                storage_object = StorageObject(
                                    id=new_uuid(),
                                    checksum=checksum,
                                    size=size,
                                    mime="image/jpeg",
                                    owner_type="video_detection",
                                    owner_id=detection_id,
                                    state="final",
                                    retention_policy="analysis_evidence",
                                    backend_key=str(crop_path),
                                )
                        pending_detections.append(
                            VideoDetection(
                                id=detection_id,
                                job_id=job.id,
                                video_id=video.id,
                                mission_id=video.mission_id,
                                org_id=video.org_id,
                                frame_index=frame.frame_index,
                                timestamp_seconds=frame.timestamp_seconds,
                                label=det.label,
                                confidence=det.confidence,
                                x1=det.x1,
                                y1=det.y1,
                                x2=det.x2,
                                y2=det.y2,
                                track_id=det.track_id,
                                lat=geo.lat,
                                lon=geo.lon,
                                altitude_m=geo.altitude_m,
                                heading_deg=geo.heading_deg,
                                evidence_path=None,
                                storage_object_id=(
                                    storage_object.id if storage_object is not None else None
                                ),
                                storage_object=storage_object,
                                raw={
                                    **det.raw,
                                    "model_version": resolved_version,
                                    "loaded_model_hash": loaded_model_hash,
                                    "small_object_mode": job.small_object_mode,
                                    "tracking_enabled": job.tracking_enabled,
                                    "tracker_type": job.tracker_type,
                                    "telemetry_match_quality": (
                                        "low_confidence_upload_time"
                                        if video.capture_time_source == "upload_time"
                                        else geo.quality
                                    ),
                                    "telemetry_match_delta_ms": geo.error_ms,
                                    "telemetry_match_method": "nearest",
                                    "telemetry_match_version": "nearest-telemetry.v1",
                                    "capture_time_source": video.capture_time_source,
                                },
                            )
                        )
                    prometheus_metrics.video_inference_queue_depth.labels(job_id=job.id).set(
                        len(pending_detections)
                    )

                if processed % 20 == 0 or len(pending_detections) >= MAX_PENDING_DETECTIONS:
                    if await self.repo.is_job_cancelled(job.id):
                        raise VideoAnalysisCancelled("Video analysis was cancelled.")
                    failure_stage = "detection_persistence"
                    persist_started = time.monotonic()
                    flushed = await self.repo.flush_batch(
                        pending_detections,
                        job=job,
                        progress=processed / estimated_total * 100.0,
                        expected_attempt=claimed_attempt,
                    )
                    stage_timings["persist"] += (
                        time.monotonic() - persist_started
                    ) * 1000.0
                    if not flushed:
                        return
                    pending_detections = []
                    failure_stage = "inference"
                    prometheus_metrics.video_inference_queue_depth.labels(job_id=job.id).set(0)

            if pending_detections:
                if await self.repo.is_job_cancelled(job.id):
                    raise VideoAnalysisCancelled("Video analysis was cancelled.")
                failure_stage = "detection_persistence"
                persist_started = time.monotonic()
                flushed = await self.repo.flush_batch(
                    pending_detections,
                    job=job,
                    progress=min(99.0, processed / estimated_total * 100.0),
                    expected_attempt=claimed_attempt,
                )
                stage_timings["persist"] += (
                    time.monotonic() - persist_started
                ) * 1000.0
                if not flushed:
                    return
                prometheus_metrics.video_inference_queue_depth.labels(job_id=job.id).set(0)
            if frames_processed == 0:
                raise RuntimeError("No video frames were successfully analyzed.")
            if tracker is not None:
                metric_record(
                    "video_unique_track_count",
                    len(tracker.global_ids),
                    {"tracker": job.tracker_type},
                )
            frames_dropped = max(0, estimated_total - frames_received)
            summary_started = time.monotonic()
            metrics_saved = await self.repo.update_processing_metrics(
                job,
                frames_received=frames_received,
                frames_decoded=frames_decoded,
                frames_attempted=frames_attempted,
                frames_processed=frames_processed,
                frames_persisted=frames_persisted,
                frames_dropped=frames_dropped,
                frames_failed=frames_failed,
                total_inference_latency_ms=total_inference_latency_ms,
                expected_attempt=claimed_attempt,
            )
            if not metrics_saved:
                return
            stage_timings["summary"] = (time.monotonic() - summary_started) * 1000.0
            stage_timings["total"] = (time.monotonic() - pipeline_started) * 1000.0
            await self._persist_stage_timings(job, stage_timings)
            for stage, duration_ms in stage_timings.items():
                metric_record(
                    "video_stage_duration",
                    duration_ms,
                    {"stage": stage},
                )
            completed = await self.repo.mark_job_completed(
                job, video=video, expected_attempt=claimed_attempt
            )
            if completed is False:
                await self.repo.cleanup_cancelled_job(job.id)
                return
            logger.info(
                "Completed video analysis job_id=%s detections=%d",
                job.id,
                detection_count,
            )

        except VideoAnalysisCancelled:
            await self.db.rollback()
            await self.repo.cleanup_cancelled_job(job.id)
            logger.info("Cancelled video analysis job_id=%s", job.id)
            return
        except Exception as exc:
            structured_error(
                logger,
                "video_analysis_failed",
                exc,
                mission_id=video.mission_id,
            )
            await self.db.rollback()
            stage_timings["total"] = (time.monotonic() - pipeline_started) * 1000.0
            metrics_saved = await self.repo.update_processing_metrics(
                job,
                frames_received=frames_received,
                frames_decoded=frames_decoded,
                frames_attempted=frames_attempted,
                frames_processed=frames_processed,
                frames_persisted=frames_persisted,
                frames_dropped=frames_dropped,
                frames_failed=max(1, frames_failed),
                total_inference_latency_ms=total_inference_latency_ms,
                expected_attempt=claimed_attempt,
            )
            if not metrics_saved:
                return
            await self._persist_stage_timings(job, stage_timings)
            error_message = (
                str(exc)
                if isinstance(exc, RuntimeError)
                and (
                    "YOLO runtime dependencies" in str(exc)
                    or "SAHI runtime" in str(exc)
                    or "Small-object analysis failed" in str(exc)
                    or "No video frames were successfully analyzed" in str(exc)
                )
                else f"Analysis failed ({type(exc).__name__}). Check worker logs for details."
            )
            await self.repo.mark_job_failed(
                job,
                error_message,
                video=video,
                reason_code=(
                    "NO_SUCCESSFUL_FRAMES"
                    if frames_processed == 0
                    else "INFERENCE_FAILED"
                ),
                stage=failure_stage,
                expected_attempt=claimed_attempt,
            )
            raise

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def should_store_crop(*, confidence: float, track_id: int | None) -> bool:
        if not settings.video_analysis_defer_low_confidence_crops:
            return True
        return (
            confidence >= settings.video_analysis_crop_min_confidence
            or track_id is not None
        )

    async def _persist_stage_timings(self, job, timings: dict[str, float]) -> None:
        setter = getattr(self.repo, "set_stage_timings", None)
        if setter is not None:
            await setter(job, timings)

    async def _iter_inference_frames(
        self,
        video_path: Path,
        *,
        every_seconds: float,
        decode_stride_enabled: bool,
        detector,
        allow_batching: bool,
    ) -> AsyncIterator[tuple[object, list | None, Exception | None, float]]:
        frames = async_iter_frames(
            video_path,
            every_seconds=every_seconds,
            decode_stride_enabled=decode_stride_enabled,
        )
        batch_size = settings.video_analysis_inference_batch_size
        predict_batch = getattr(detector, "predict_batch", None)
        if batch_size <= 1 or not allow_batching or predict_batch is None:
            async for frame in frames:
                yield frame, None, None, 0.0
            return

        pending = []
        async for frame in frames:
            pending.append(frame)
            if len(pending) >= batch_size:
                async for item in self._run_inference_batch(pending, predict_batch):
                    yield item
                pending = []
        if pending:
            async for item in self._run_inference_batch(pending, predict_batch):
                yield item

    async def _run_inference_batch(
        self, frames: list, predict_batch
    ) -> AsyncIterator[tuple[object, list | None, Exception | None, float]]:
        started = time.monotonic()
        try:
            results = await run_blocking(
                predict_batch,
                [frame.image_bgr for frame in frames],
                boundary="cpu",
                operation="video_inference_batch",
                timeout_s=120.0,
            )
            if len(results) != len(frames):
                raise RuntimeError("Detector batch returned an unexpected result count.")
            per_frame_latency_ms = (time.monotonic() - started) * 1000.0 / len(frames)
            for frame, detections in zip(frames, results, strict=True):
                yield frame, detections, None, per_frame_latency_ms
        except Exception as exc:
            per_frame_latency_ms = (time.monotonic() - started) * 1000.0 / len(frames)
            for frame in frames:
                yield frame, None, exc, per_frame_latency_ms

    def _save_crop(
        self,
        *,
        job_id: str,
        frame_index: int,
        detection_index: int,
        image_bgr: NDArray,
        xyxy: tuple[float, float, float, float],
    ) -> tuple[Path, str, int] | None:
        x1, y1, x2, y2 = [round(v) for v in xyxy]
        h, w = image_bgr.shape[:2]

        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))

        if x2 <= x1 or y2 <= y1:
            return None

        crop = image_bgr[y1:y2, x1:x2]
        out_dir = self.evidence_root / "crops" / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"frame_{frame_index:08d}_det_{detection_index:03d}.jpg"
        if not cv2.imwrite(str(out_path), crop) or not out_path.is_file():
            out_path.unlink(missing_ok=True)
            raise RuntimeError("Detection crop write failed.")
        return out_path, self._sha256_file(out_path), out_path.stat().st_size

    def _clear_prior_evidence(self, job_id: str) -> None:
        crop_dir = self.evidence_root / "crops" / job_id
        if crop_dir.exists():
            shutil.rmtree(crop_dir)


async def run_video_analysis_job(job_id: str) -> dict[str, str]:
    async with Session() as db:
        pipeline = OfflineVideoAnalysisPipeline(db)
        await pipeline.run(job_id)
        job = await pipeline.repo.get_job(job_id)
    return {"job_id": job_id, "status": job.status if job is not None else "missing"}
