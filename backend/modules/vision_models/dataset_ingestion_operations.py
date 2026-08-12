from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from uuid import uuid4

import cv2
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.agriculture.ports.telemetry import (
    list_mission_telemetry_for_georef,
)
from backend.modules.identity.models import User
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.service.geo import NearestTelemetryMatcher
from backend.modules.vision_models.application_base import (
    VisionConflict,
    VisionNotFound,
    VisionValidationError,
)
from backend.modules.vision_models.config import vision_settings
from backend.modules.vision_models.models import DatasetImage, DatasetVersion
from backend.modules.vision_models.repository import VisionRepository
from backend.modules.vision_models.schemas import ExtractFramesRequest, ImageUploadResult
from backend.modules.vision_models.service.dataset_service import (
    DatasetServiceError,
    assign_deterministic_splits,
    prepare_uploaded_image,
    write_manifest,
)
from backend.modules.vision_models.service.frame_curation import curate_video_frames

logger = logging.getLogger(__name__)


class DatasetIngestionOperations:
    async def _refresh_dataset(self, db: AsyncSession, dataset: DatasetVersion) -> None:
        repo = VisionRepository(db)
        await db.flush()
        images = await repo.all_dataset_images(dataset.id)
        split_summary = (getattr(dataset, "curation_summary", None) or {}).get(
            "split_leakage", {}
        )
        if dataset.status != "locked":
            split_summary = assign_deterministic_splits(images)
        selected = [image for image in images if image.selected]
        dataset.image_count = len(images)
        dataset.source_count = len({image.source_group for image in images})
        dataset.labeled_count = sum(
            image.annotation_status in {"labeled", "reviewed"} for image in images
        )
        dataset.reviewed_count = sum(
            image.annotation_status == "reviewed" for image in images
        )
        dataset.train_count = sum(image.split == "train" for image in selected)
        dataset.val_count = sum(image.split == "val" for image in selected)
        dataset.test_count = sum(image.split == "test" for image in selected)
        quality_rows = [
            image.metadata_json.get("quality", {})
            for image in images
            if isinstance(image.metadata_json, dict)
        ]
        blur = [
            float(row["blur_variance"])
            for row in quality_rows
            if isinstance(row.get("blur_variance"), (int, float))
        ]
        exposure = [
            float(row["mean_exposure"])
            for row in quality_rows
            if isinstance(row.get("mean_exposure"), (int, float))
        ]
        duplicate_clusters = {
            image.metadata_json.get("duplicate_cluster_id")
            for image in images
            if isinstance(image.metadata_json, dict)
            and image.metadata_json.get("duplicate_cluster_id")
        }
        dataset.curation_summary = {
            "policy_version": "vision-data-quality.v1",
            "duplicate_cluster_count": len(duplicate_clusters),
            "split_leakage": split_summary,
            "split_leakage_risk": bool(
                split_summary.get("nearest_cross_split_similarity_count", 0)
            ),
            "blur": {
                "minimum": min(blur) if blur else None,
                "mean": sum(blur) / len(blur) if blur else None,
            },
            "exposure": {
                "minimum": min(exposure) if exposure else None,
                "maximum": max(exposure) if exposure else None,
                "mean": sum(exposure) / len(exposure) if exposure else None,
            },
            "quality_flags": {
                "split_leakage_risk": bool(
                    split_summary.get("nearest_cross_split_similarity_count", 0)
                )
            },
        }
        dataset.manifest_checksum = await run_blocking(
            write_manifest,
            dataset,
            dataset.project_id,
            images,
            self.storage,
            boundary="filesystem",
            operation="write_vision_manifest",
            timeout_s=60,
        )
        await db.flush()

    async def upload_images(
        self,
        db: AsyncSession,
        dataset_id: str,
        files: list,
        user: User,
    ) -> ImageUploadResult:
        if not files or len(files) > vision_settings.vision_max_images_per_request:
            raise VisionValidationError(
                f"Upload between 1 and {vision_settings.vision_max_images_per_request} images"
            )
        repo = VisionRepository(db)
        dataset = await repo.get_dataset(dataset_id, user)
        if dataset is None:
            raise VisionNotFound("Dataset not found")
        self._assert_mutable(dataset)
        source_group = f"upload:{uuid4()}"
        existing_hashes = set(
            (
                await db.scalars(
                    select(DatasetImage.sha256).where(
                        DatasetImage.dataset_id == dataset.id
                    )
                )
            ).all()
        )
        added: list[DatasetImage] = []
        duplicates = 0
        rejected: list[str] = []
        for file in files:
            filename = Path(file.filename or "image").name
            content = await file.read(vision_settings.vision_max_image_bytes + 1)
            await file.close()
            if len(content) > vision_settings.vision_max_image_bytes:
                rejected.append(f"{filename}: exceeds the 20 MB image limit")
                continue
            try:
                prepared = await run_blocking(
                    prepare_uploaded_image,
                    content,
                    filename=filename,
                    content_type=file.content_type,
                    project_id=dataset.project_id,
                    dataset_version=dataset.version,
                    storage=self.storage,
                    boundary="media",
                    operation="prepare_vision_image",
                    timeout_s=60,
                )
            except DatasetServiceError as exc:
                rejected.append(str(exc))
                continue
            if prepared.sha256 in existing_hashes:
                duplicates += 1
                self.storage.resolve_uri(prepared.storage_uri).unlink(missing_ok=True)
                self.storage.resolve_uri(prepared.thumbnail_uri).unlink(missing_ok=True)
                continue
            existing_hashes.add(prepared.sha256)
            quality_reasons = prepared.metadata.get("quality", {}).get(
                "rejection_reasons", []
            )
            image = DatasetImage(
                dataset_id=dataset.id,
                storage_uri=prepared.storage_uri,
                thumbnail_uri=prepared.thumbnail_uri,
                source_type="upload",
                source_group=source_group,
                width=prepared.width,
                height=prepared.height,
                sha256=prepared.sha256,
                perceptual_hash=prepared.perceptual_hash,
                quality_score=prepared.quality_score,
                selected=not bool(quality_reasons),
                metadata_json=prepared.metadata,
            )
            if quality_reasons:
                rejected.append(
                    f"{filename}: {', '.join(quality_reasons)} (kept but excluded)"
                )
            db.add(image)
            added.append(image)
        await self._refresh_dataset(db, dataset)
        await db.commit()
        for image in added:
            await db.refresh(image, attribute_names=["annotations"])
        logger.info(
            "Vision images uploaded dataset_id=%s added=%d duplicates=%d rejected=%d",
            dataset.id,
            len(added),
            duplicates,
            len(rejected),
        )
        return ImageUploadResult(
            added=len(added),
            duplicates=duplicates,
            rejected=rejected,
            images=[self.image_output(image) for image in added],
        )

    @staticmethod
    def _make_thumbnail(source: Path, target: Path) -> None:
        image = cv2.imread(str(source))
        if image is None:
            raise DatasetServiceError("Extracted frame could not be read")
        height, width = image.shape[:2]
        thumb_width = min(360, width)
        thumb_height = max(1, round(height * thumb_width / width))
        thumbnail = cv2.resize(
            image, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 82]):
            raise DatasetServiceError("Thumbnail could not be written")

    async def extract_frames(
        self,
        db: AsyncSession,
        dataset_id: str,
        payload: ExtractFramesRequest,
        user: User,
    ) -> dict:
        repo = VisionRepository(db)
        dataset = await repo.get_dataset(dataset_id, user)
        if dataset is None:
            raise VisionNotFound("Dataset not found")
        self._assert_mutable(dataset)
        video = await VideoAnalysisRepository(db).get_video_for_user(
            payload.video_id, user
        )
        if video is None:
            raise VisionNotFound("Video not found")
        imported = await db.scalar(
            select(func.count())
            .select_from(DatasetImage)
            .where(
                DatasetImage.dataset_id == dataset.id,
                DatasetImage.source_video_id == video.id,
            )
        )
        if imported:
            raise VisionConflict("This video is already part of the dataset")
        max_frames = min(
            payload.max_frames or vision_settings.vision_max_extraction_frames,
            vision_settings.vision_max_extraction_frames,
        )
        output = self.storage.project_path(
            dataset.project_id,
            "datasets",
            f"v{dataset.version}",
            "images",
            video.id,
        )
        result = await run_blocking(
            curate_video_frames,
            video.storage_path,
            output,
            interval_seconds=payload.interval_seconds,
            max_frames=max_frames,
            boundary="media",
            operation="curate_vision_frames",
            timeout_s=900,
        )
        telemetry_samples = (
            await list_mission_telemetry_for_georef(
                db, mission_id=video.mission_id
            )
            if video.mission_id
            else []
        )
        telemetry = NearestTelemetryMatcher(
            video.mission_id,
            telemetry_samples,
            getattr(video, "captured_at", None) or video.created_at,
        )
        for frame in result.frames:
            path = Path(frame.path)
            thumbnail = self.storage.project_path(
                dataset.project_id,
                "datasets",
                f"v{dataset.version}",
                "thumbnails",
                video.id,
                path.name,
            )
            await run_blocking(
                self._make_thumbnail,
                path,
                thumbnail,
                boundary="media",
                operation="create_vision_thumbnail",
                timeout_s=30,
            )
            content = path.read_bytes()
            geo = telemetry.match(frame.timestamp_seconds)
            db.add(
                DatasetImage(
                    dataset_id=dataset.id,
                    storage_uri=self.storage.to_uri(path),
                    thumbnail_uri=self.storage.to_uri(thumbnail),
                    source_type="video_frame",
                    source_group=f"video:{video.id}",
                    source_video_id=video.id,
                    mission_id=video.mission_id,
                    field_id=video.field_id,
                    frame_index=frame.frame_index,
                    timestamp_seconds=frame.timestamp_seconds,
                    width=frame.width,
                    height=frame.height,
                    sha256=hashlib.sha256(content).hexdigest(),
                    perceptual_hash=frame.perceptual_hash,
                    quality_score=frame.quality.score,
                    selected=frame.selected,
                    lat=geo.lat,
                    lon=geo.lon,
                    altitude_m=geo.altitude_m,
                    heading_deg=geo.heading_deg,
                    metadata_json={
                        "quality": {
                            "blur_variance": frame.quality.blur_variance,
                            "mean_exposure": frame.quality.mean_exposure,
                        },
                        "telemetry_match_quality": geo.quality,
                        "telemetry_error_ms": geo.error_ms,
                        "capture_time_source": (
                            getattr(video, "capture_time_source", None)
                            if getattr(video, "captured_at", None)
                            else "upload_time_fallback"
                        ),
                        "duplicate_cluster_id": frame.duplicate_cluster_id,
                    },
                )
            )
        manifest = self.storage.project_path(
            dataset.project_id,
            "datasets",
            f"v{dataset.version}",
            "curation",
            f"{video.id}.json",
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(result.manifest(), indent=2, sort_keys=True), encoding="utf-8"
        )
        await self._refresh_dataset(db, dataset)
        await db.commit()
        await db.refresh(dataset)
        logger.info(
            "Vision frames curated dataset_id=%s video_id=%s selected=%d",
            dataset.id,
            video.id,
            len(result.selected),
        )
        return {
            "candidate_frames": result.candidate_frames,
            "rejected_quality": result.rejected_quality,
            "rejected_duplicates": result.rejected_duplicates,
            "selected_frames": len(result.selected),
            "effective_interval_seconds": result.effective_interval_seconds,
            "duplicate_cluster_count": result.duplicate_cluster_count,
            "comparison_count": result.comparison_count,
            "dataset": self.dataset_output(dataset),
        }
