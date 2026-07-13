from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path

import cv2
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import Session
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.video_analysis.models import VideoDetection
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.service.detector import YoloFrameDetector
from backend.modules.video_analysis.service.frame_extractor import (
    async_iter_frames,
    read_video_metadata_async,
)
from backend.modules.video_analysis.service.geo import NearestTelemetryMatcher
from backend.observability import prometheus_metrics
from backend.observability.instruments import observed_span, structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

logger = logging.getLogger(__name__)
MAX_PENDING_DETECTIONS = 100


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

        video = await self.repo.get_video(job.video_id)
        if video is None:
            raise ValueError(f"VideoAsset not found: {job.video_id}")

        await run_blocking(
            self._clear_prior_evidence,
            job.id,
            boundary="filesystem",
            operation="clear_video_evidence",
            timeout_s=30.0,
        )
        await self.repo.mark_job_running(job)
        frames_received = 0
        frames_processed = 0
        frames_dropped = 0
        frames_failed = 0
        total_inference_latency_ms = 0.0

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
            with observed_span(
                "video.metadata",
                mission_id=video.mission_id,
                camera_name="offline_video",
                **{"model.name": job.model_name},
            ):
                metadata = await read_video_metadata_async(video_path)
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

            detector = await run_blocking(
                YoloFrameDetector,
                model_name=job.model_name,
                confidence_threshold=job.confidence_threshold,
                boundary="media",
                operation="load_detector",
                timeout_s=120.0,
            )
            await self.repo.set_model_version(job, detector.model_version)
            telemetry = NearestTelemetryMatcher(video.mission_id)

            pending_detections: list[VideoDetection] = []
            detection_count = 0
            estimated_total = max(
                1,
                int(metadata.duration_seconds / max(job.frame_stride_seconds, 0.1)),
            )

            processed = 0
            async for frame in async_iter_frames(
                video_path,
                every_seconds=job.frame_stride_seconds,
            ):
                processed += 1
                frames_received += 1
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
                        frame_detections = await run_blocking(
                            detector.predict,
                            frame.image_bgr,
                            boundary="cpu",
                            operation="video_inference",
                            timeout_s=120.0,
                        )
                    except Exception:
                        frames_failed += 1
                        total_inference_latency_ms += (
                            time.monotonic() - inference_started
                        ) * 1000.0
                        logger.exception(
                            "Video frame inference failed job_id=%s frame_index=%s",
                            job.id,
                            frame.frame_index,
                        )
                        continue
                    inference_latency_ms = (time.monotonic() - inference_started) * 1000.0
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
                geo = telemetry.match(frame.timestamp_seconds)

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
                        evidence_path = await run_blocking(
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

                    pending_detections.append(
                        VideoDetection(
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
                            lat=geo.lat,
                            lon=geo.lon,
                            altitude_m=geo.altitude_m,
                            heading_deg=geo.heading_deg,
                            evidence_path=str(evidence_path) if evidence_path else None,
                            raw=det.raw,
                        )
                    )
                    prometheus_metrics.video_inference_queue_depth.labels(job_id=job.id).set(
                        len(pending_detections)
                    )

                if processed % 20 == 0 or len(pending_detections) >= MAX_PENDING_DETECTIONS:
                    await self.repo.flush_batch(
                        pending_detections,
                        job=job,
                        progress=processed / estimated_total * 100.0,
                    )
                    pending_detections = []
                    prometheus_metrics.video_inference_queue_depth.labels(job_id=job.id).set(0)

            if pending_detections:
                await self.repo.flush_batch(pending_detections)
                prometheus_metrics.video_inference_queue_depth.labels(job_id=job.id).set(0)
            frames_dropped = max(0, estimated_total - frames_received)
            await self.repo.update_processing_metrics(
                job,
                frames_received=frames_received,
                frames_processed=frames_processed,
                frames_dropped=frames_dropped,
                frames_failed=frames_failed,
                total_inference_latency_ms=total_inference_latency_ms,
            )
            await self.repo.set_video_status(video, "analyzed")
            await self.repo.mark_job_completed(job)
            logger.info(
                "Completed video analysis job_id=%s detections=%d",
                job.id,
                detection_count,
            )

        except Exception as exc:
            structured_error(
                logger,
                "video_analysis_failed",
                exc,
                mission_id=video.mission_id,
            )
            await self.db.rollback()
            await self.repo.update_processing_metrics(
                job,
                frames_received=frames_received,
                frames_processed=frames_processed,
                frames_dropped=frames_dropped,
                frames_failed=max(1, frames_failed),
                total_inference_latency_ms=total_inference_latency_ms,
            )
            error_message = (
                str(exc)
                if isinstance(exc, RuntimeError) and "YOLO runtime dependencies" in str(exc)
                else f"Analysis failed ({type(exc).__name__}). Check worker logs for details."
            )
            await self.repo.mark_job_failed(
                job,
                error_message,
            )
            raise

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _save_crop(
        self,
        *,
        job_id: str,
        frame_index: int,
        detection_index: int,
        image_bgr,
        xyxy: tuple[float, float, float, float],
    ) -> Path | None:
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
        cv2.imwrite(str(out_path), crop)
        return out_path

    def _clear_prior_evidence(self, job_id: str) -> None:
        crop_dir = self.evidence_root / "crops" / job_id
        if crop_dir.exists():
            shutil.rmtree(crop_dir)


async def run_video_analysis_job(job_id: str) -> dict[str, str]:
    async with Session() as db:
        await OfflineVideoAnalysisPipeline(db).run(job_id)
    return {"job_id": job_id, "status": "completed"}
