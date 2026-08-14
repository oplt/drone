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
from backend.modules.agriculture.georeferencing import NearestTelemetryMatcher
from backend.modules.agriculture.ports.telemetry import (
    list_mission_telemetry_for_georef,
)
from backend.modules.identity.models import User
from backend.modules.video_analysis.contracts import video_analysis_port
from backend.modules.vision_models.application_base import (
    VisionConflict,
    VisionNotFound,
    VisionValidationError,
)
from backend.modules.vision_models.config import vision_settings
from backend.modules.vision_models.models import (
    DatasetImage,
    DatasetVersion,
    VisionStorageObject,
)
from backend.modules.vision_models.repository import VisionRepository
from backend.modules.vision_models.schemas import ExtractFramesRequest, ImageUploadResult
from backend.modules.vision_models.service.dataset_service import (
    DatasetServiceError,
    apply_dataset_near_duplicate_clustering,
    assign_deterministic_splits,
    count_cross_split_near_duplicates,
    prepare_uploaded_image,
    source_distribution,
    write_manifest,
)
from backend.modules.vision_models.service.frame_curation import curate_video_frames

logger = logging.getLogger(__name__)


class DatasetIngestionOperations:
    def _register_storage_object(
        self,
        db: AsyncSession,
        *,
        path: Path,
        owner_type: str,
        owner_id: str,
        checksum: str | None = None,
    ) -> VisionStorageObject:
        item = VisionStorageObject(
            checksum=checksum or hashlib.sha256(path.read_bytes()).hexdigest(),
            size=int(path.stat().st_size),
            mime="image/jpeg",
            owner_type=owner_type,
            owner_id=owner_id,
            state="final",
            retention_policy="dataset_media",
            backend_key=self.storage.to_uri(path).removeprefix("vision://"),
        )
        db.add(item)
        return item

    async def _refresh_dataset(self, db: AsyncSession, dataset: DatasetVersion) -> None:
        repo = VisionRepository(db)
        await db.flush()
        images = await repo.all_dataset_images(dataset.id)
        mutate = dataset.status != "locked"
        if mutate:
            cluster_summary = apply_dataset_near_duplicate_clustering(
                images, mutate_selection=True
            )
            split_summary = assign_deterministic_splits(images)
        else:
            cluster_ids = sorted(
                {
                    image.metadata_json.get("duplicate_cluster_id")
                    for image in images
                    if isinstance(image.metadata_json, dict)
                    and image.metadata_json.get("duplicate_cluster_id")
                }
            )
            prior_split = (getattr(dataset, "curation_summary", None) or {}).get(
                "split_leakage", {}
            )
            cluster_summary = {
                "duplicate_cluster_count": len(cluster_ids),
                "near_duplicate_rejected": 0,
                "comparison_count": 0,
                "near_duplicate_clusters": [
                    {"cluster_id": cluster_id, "size": 0, "image_ids": []}
                    for cluster_id in cluster_ids
                ],
            }
            split_summary = {
                "held_boundary_frames": int(prior_split.get("held_boundary_frames", 0) or 0),
                "nearest_cross_split_similarity_count": count_cross_split_near_duplicates(
                    images
                ),
            }
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
        quality_exclusions = sum(
            1
            for image in images
            if isinstance(image.metadata_json, dict)
            and (image.metadata_json.get("quality") or {}).get("rejection_reasons")
            and not image.selected
        )
        leakage_count = int(
            split_summary.get("nearest_cross_split_similarity_count", 0) or 0
        )
        split_leakage_risk = leakage_count > 0
        dataset.curation_summary = {
            "policy_version": "vision-data-quality.v1",
            "duplicate_cluster_count": cluster_summary.get("duplicate_cluster_count", 0),
            "near_duplicate_clusters": cluster_summary.get("near_duplicate_clusters", []),
            "near_duplicate_rejected": cluster_summary.get("near_duplicate_rejected", 0),
            "comparison_count": cluster_summary.get("comparison_count", 0),
            "excluded_images": sum(1 for image in images if not image.selected),
            "quality_exclusions": quality_exclusions,
            "split_leakage": split_summary,
            "split_leakage_risk": split_leakage_risk,
            "source_distribution": source_distribution(images),
            "blur": {
                "minimum": min(blur) if blur else None,
                "mean": sum(blur) / len(blur) if blur else None,
            },
            "exposure": {
                "minimum": min(exposure) if exposure else None,
                "maximum": max(exposure) if exposure else None,
                "mean": sum(exposure) / len(exposure) if exposure else None,
            },
            # Blocking flags only — resolved near-dupe clusters are informational.
            "quality_flags": {
                "split_leakage_risk": split_leakage_risk,
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
            image_id = str(uuid4())
            storage_object = self._register_storage_object(
                db,
                path=self.storage.resolve_uri(prepared.storage_uri),
                owner_type="dataset_image",
                owner_id=image_id,
                checksum=prepared.sha256,
            )
            thumbnail_object = self._register_storage_object(
                db,
                path=self.storage.resolve_uri(prepared.thumbnail_uri),
                owner_type="dataset_thumbnail",
                owner_id=image_id,
            )
            image = DatasetImage(
                id=image_id,
                dataset_id=dataset.id,
                storage_uri=prepared.storage_uri,
                thumbnail_uri=prepared.thumbnail_uri,
                storage_object=storage_object,
                thumbnail_storage_object=thumbnail_object,
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
        video = await video_analysis_port.get_source_for_user(
            db, payload.video_id, user
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
        try:
            video_path = await video_analysis_port.resolve_source_media_path(
                db,
                video_id=video.id,
                org_id=user.org_id,
            )
        except LookupError as exc:
            raise VisionNotFound("Video source is unavailable") from exc
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
            video_path,
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
            video.captured_at or video.created_at,
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
            image_id = str(uuid4())
            storage_object = self._register_storage_object(
                db,
                path=path,
                owner_type="dataset_image",
                owner_id=image_id,
                checksum=hashlib.sha256(content).hexdigest(),
            )
            thumbnail_object = self._register_storage_object(
                db,
                path=thumbnail,
                owner_type="dataset_thumbnail",
                owner_id=image_id,
            )
            db.add(
                DatasetImage(
                    id=image_id,
                    dataset_id=dataset.id,
                    storage_uri=self.storage.to_uri(path),
                    thumbnail_uri=self.storage.to_uri(thumbnail),
                    storage_object=storage_object,
                    thumbnail_storage_object=thumbnail_object,
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
                            video.capture_time_source
                            if video.captured_at
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
