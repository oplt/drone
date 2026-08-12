from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.agriculture.capabilities import (
    agriculture_capability_release_service,
)
from backend.modules.identity.dependencies import ORG_WRITE_ROLES
from backend.modules.identity.models import User
from backend.modules.vision_models.application_base import (
    PRESETS,
    VisionConflict,
    VisionNotFound,
    VisionValidationError,
    VisionWorkerUnavailable,
)
from backend.modules.vision_models.config import vision_settings
from backend.modules.vision_models.models import (
    DatasetVersion,
    ModelVersion,
    TrainingRun,
    VisionProject,
)
from backend.modules.vision_models.release_policy import evaluate_release
from backend.modules.vision_models.release_read_port import model_release_from_orm
from backend.modules.vision_models.repository import VisionRepository
from backend.modules.vision_models.schemas import (
    ModelEvaluationOut,
    ModelVersionOut,
    TrainingRunCreate,
    TrainingRunOut,
)
from backend.modules.vision_models.service.dataset_service import (
    assign_deterministic_splits,
)
from backend.modules.vision_models.service.queue import VisionTrainingQueueError
from backend.modules.vision_models.service.storage import VisionStorageError

logger = logging.getLogger(__name__)


class TrainingOperations:
    async def create_training_run(
        self,
        db: AsyncSession,
        project_id: str,
        payload: TrainingRunCreate,
        user: User,
    ) -> TrainingRunOut:
        repo = VisionRepository(db)
        project = await repo.get_project(project_id, user)
        dataset = await repo.get_dataset(payload.dataset_id, user)
        if project is None or dataset is None or dataset.project_id != project.id:
            raise VisionNotFound("Project or dataset not found")
        images = await repo.all_dataset_images(dataset.id)
        selected = [image for image in images if image.selected]
        if len(selected) < 3:
            raise VisionValidationError("At least three selected images are required")
        if any(image.annotation_status != "reviewed" for image in selected):
            raise VisionValidationError("Review every selected image before training")
        curation = getattr(dataset, "curation_summary", None) or {}
        quality_flags = (
            curation.get("quality_flags", {}) if isinstance(curation, dict) else {}
        )
        split_leakage_risk = bool(
            (curation.get("split_leakage_risk") if isinstance(curation, dict) else False)
            or (quality_flags.get("split_leakage_risk") if isinstance(quality_flags, dict) else False)
        )
        if vision_settings.vision_require_curation_quality and (
            split_leakage_risk
            or (
                isinstance(quality_flags, dict)
                and any(bool(value) for value in quality_flags.values())
            )
        ):
            raise VisionValidationError(
                "Dataset curation quality flags must be resolved before training"
            )
        if dataset.status != "locked":
            assign_deterministic_splits(images)
        split_counts = {
            split: sum(image.split == split for image in selected)
            for split in ("train", "val", "test")
        }
        if any(count == 0 for count in split_counts.values()):
            raise VisionValidationError("Dataset requires train, validation, and test images")
        active = await db.scalar(
            select(func.count())
            .select_from(TrainingRun)
            .join(VisionProject)
            .where(
                VisionRepository.project_visible_to(user),
                TrainingRun.status.in_(("queued", "running", "cancelling")),
            )
        )
        if int(active or 0) >= vision_settings.vision_max_active_training_runs_per_org:
            raise VisionConflict("The organization already has an active training run")
        preset = PRESETS[payload.preset]
        if dataset.status != "locked":
            dataset.status = "locked"
            dataset.locked_at = datetime.now(UTC)
        await self._refresh_dataset(db, dataset)
        run = TrainingRun(
            project_id=project.id,
            dataset_id=dataset.id,
            status="queued",
            trainer="ultralytics",
            base_model=payload.base_model,
            preset=payload.preset,
            epochs=preset["epochs"],
            image_size=preset["image_size"],
            batch_size=preset["batch_size"],
            device="auto",
            config={
                "dataset_checksum": dataset.manifest_checksum,
                "classes": [item.name for item in project.classes],
                "augmentation": {
                    "hsv_h": 0.0,
                    "hsv_s": 0.1,
                    "hsv_v": 0.2,
                    "fliplr": 0.5,
                    "flipud": 0.1,
                },
            },
            created_by_user_id=user.id,
        )
        db.add(run)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise VisionConflict(
                "This project already has a queued, running, or cancelling training run"
            ) from exc
        try:
            run.queue_task_id = self.queue.enqueue(run.id)
            await db.commit()
        except VisionTrainingQueueError as exc:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            await db.commit()
            raise VisionWorkerUnavailable(str(exc)) from exc
        await db.refresh(run, attribute_names=["model_version"])
        logger.info(
            "Vision training queued run_id=%s project_id=%s dataset_id=%s preset=%s",
            run.id,
            project.id,
            dataset.id,
            run.preset,
        )
        return self.training_output(run)

    async def get_training_run(
        self, db: AsyncSession, run_id: str, user: User
    ) -> TrainingRunOut:
        run = await VisionRepository(db).get_training_run(run_id, user)
        if run is None:
            raise VisionNotFound("Training run not found")
        return self.training_output(run)

    async def list_training_runs(
        self, db: AsyncSession, project_id: str, user: User
    ) -> list[TrainingRunOut]:
        if await VisionRepository(db).get_project(project_id, user) is None:
            raise VisionNotFound("Vision project not found")
        runs = await VisionRepository(db).list_training_runs(project_id, user)
        return [self.training_output(run) for run in runs]

    async def cancel_training_run(
        self, db: AsyncSession, run_id: str, user: User
    ) -> TrainingRunOut:
        run = await VisionRepository(db).get_training_run(run_id, user)
        if run is None:
            raise VisionNotFound("Training run not found")
        if run.status not in {"queued", "running"}:
            raise VisionConflict("Only queued or running training can be cancelled")
        was_queued = run.status == "queued"
        run.status = "cancelled" if was_queued else "cancelling"
        if run.status == "cancelled":
            run.finished_at = datetime.now(UTC)
            run.terminal_reason_code = "USER_CANCELLED"
            run.terminal_stage = "queued"
        if was_queued and run.queue_task_id:
            self.queue.revoke(run.queue_task_id)
        await db.commit()
        return self.training_output(run)

    async def list_models(
        self, db: AsyncSession, user: User
    ) -> list[ModelVersionOut]:
        versions = await VisionRepository(db).list_model_versions(user)
        return [self.model_output(version) for version in versions]

    async def list_model_versions(
        self, db: AsyncSession, model_id: str, user: User
    ) -> list[ModelVersionOut]:
        versions = await VisionRepository(db).list_versions_for_model(model_id, user)
        if not versions:
            raise VisionNotFound("Vision model not found")
        return [self.model_output(version) for version in versions]

    async def _verify_weights_checksum(self, weights_uri: str, expected: str) -> bool:
        try:
            path = self.storage.resolve_uri(weights_uri)
        except VisionStorageError:
            return False
        if not path.is_file():
            return False
        checksum = await run_blocking(
            lambda value: hashlib.sha256(value.read_bytes()).hexdigest(),
            path,
            boundary="filesystem",
            operation="verify_deploy_model_checksum",
            timeout_s=120,
        )
        return checksum == expected

    async def deploy_model(
        self,
        db: AsyncSession,
        version_id: str,
        user: User,
        *,
        override: bool = False,
        reason: str | None = None,
        action: str = "deploy",
    ) -> ModelVersionOut:
        repo = VisionRepository(db)
        version = await repo.get_model_version(version_id, user, for_update=True)
        if version is None:
            raise VisionNotFound("Model version not found")
        if version.status == "archived":
            raise VisionConflict("Archived model versions cannot be deployed")
        if override and (
            getattr(user, "role", None) not in ORG_WRITE_ROLES
            or not (reason and str(reason).strip())
        ):
            raise VisionConflict("Release overrides require an authorized role and reason")

        previous = await db.scalar(
            select(ModelVersion)
            .where(
                ModelVersion.model_id == version.model_id,
                ModelVersion.status == "production",
                ModelVersion.id != version.id,
            )
            .with_for_update()
        )
        dataset = await db.get(DatasetVersion, version.dataset_id)
        artifact_verified = await self._verify_weights_checksum(
            version.weights_uri, version.checksum
        )
        production_summary = (
            previous.metrics.get("summary", {}) if previous is not None else {}
        )
        production_map50 = production_summary.get("map50")
        capability_id = version.model.project.capability_id
        policy = evaluate_release(
            status=version.status,
            metrics=version.metrics,
            weights_uri=version.weights_uri,
            checksum=version.checksum,
            capability_id=capability_id,
            minimum_map50=vision_settings.vision_release_min_map50,
            training_run_id=version.training_run_id,
            dataset_id=version.dataset_id,
            dataset_version=dataset.version if dataset is not None else None,
            dataset_manifest_checksum=(
                dataset.manifest_checksum if dataset is not None else None
            ),
            test_count=dataset.test_count if dataset is not None else None,
            artifact_verified=artifact_verified,
            production_map50=(
                float(production_map50)
                if isinstance(production_map50, (int, float))
                else None
            ),
            max_map50_regression=vision_settings.vision_max_map50_regression,
            task_type=version.model.task_type,
            classes=version.classes,
        )
        if not policy.eligible and not override:
            raise VisionValidationError("; ".join(policy.reasons))
        await db.execute(
            update(ModelVersion)
            .where(
                ModelVersion.model_id == version.model_id,
                ModelVersion.id != version.id,
                ModelVersion.status == "production",
            )
            .values(status="candidate")
        )
        audit = {
            "action": action,
            "policy_version": policy.policy_version,
            "actor": user.id,
            "reason": reason,
            "rationale": reason,
            "override": override,
            "failed_checks": list(policy.reasons),
            "policy_reasons": list(policy.reasons),
            "metrics_snapshot": policy.metrics_snapshot,
            "previous_production_id": previous.id if previous else None,
            "artifact_checksum": version.checksum,
            "checksums": {
                "model": version.checksum,
                "dataset": dataset.manifest_checksum if dataset is not None else None,
            },
            "capability_id": capability_id,
            "classes": list(version.classes or []),
            "inference_contract": policy.inference_contract,
            "at": datetime.now(UTC).isoformat(),
        }
        version.metrics = {
            **version.metrics,
            "deployment_audit": [
                *version.metrics.get("deployment_audit", []),
                audit,
            ],
        }
        version.status = "production"
        try:
            await agriculture_capability_release_service.activate_for_model_version(
                db,
                version=model_release_from_orm(version),
                org_id=user.org_id,
                user_id=user.id,
            )
        except ValueError as exc:
            raise VisionValidationError(str(exc)) from exc
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise VisionConflict(
                "Another model was deployed for this capability. Refresh and retry."
            ) from exc
        refreshed = await repo.get_model_version(version.id, user)
        if refreshed is None:
            raise VisionNotFound("Model version not found")
        logger.info(
            "Vision model deployed model_id=%s version_id=%s version=%d org_id=%s",
            refreshed.model_id,
            refreshed.id,
            refreshed.version,
            user.org_id,
        )
        return self.model_output(refreshed)

    async def archive_model(
        self,
        db: AsyncSession,
        version_id: str,
        user: User,
        *,
        override: bool = False,
        reason: str | None = None,
    ) -> ModelVersionOut:
        repo = VisionRepository(db)
        version = await repo.get_model_version(version_id, user, for_update=True)
        if version is None:
            raise VisionNotFound("Model version not found")
        if version.status == "production":
            if not override:
                raise VisionConflict(
                    "The sole production model cannot be archived without a replacement"
                )
            if getattr(user, "role", None) not in ORG_WRITE_ROLES or not reason:
                raise VisionConflict(
                    "Production archive overrides require an authorized role and reason"
                )
            version.metrics = {
                **version.metrics,
                "deployment_audit": [
                    *version.metrics.get("deployment_audit", []),
                    {
                        "action": "archive_override",
                        "policy_version": "vision-release-policy.v1",
                        "actor": user.id,
                        "metrics_snapshot": version.metrics.get("summary", {}),
                        "previous_production_id": version.id,
                        "rationale": reason,
                        "override": True,
                        "artifact_checksum": version.checksum,
                        "at": datetime.now(UTC).isoformat(),
                    },
                ],
            }
        await agriculture_capability_release_service.retire_for_model_version(
            db, vision_model_version_id=version.id
        )
        version.status = "archived"
        await db.commit()
        refreshed = await repo.get_model_version(version.id, user)
        if refreshed is None:
            raise VisionNotFound("Model version not found")
        return self.model_output(refreshed)

    async def rollback_model(
        self, db: AsyncSession, version_id: str, user: User, *, reason: str | None = None
    ) -> ModelVersionOut:
        current = await VisionRepository(db).get_model_version(
            version_id, user, for_update=True
        )
        if current is None:
            raise VisionNotFound("Model version not found")
        audits = current.metrics.get("deployment_audit", [])
        previous_id = next(
            (
                item.get("previous_production_id")
                for item in reversed(audits)
                if isinstance(item, dict) and item.get("previous_production_id")
            ),
            None,
        )
        if previous_id is None:
            raise VisionConflict("No previous production model is available for rollback")
        target = await VisionRepository(db).get_model_version(previous_id, user)
        if target is None or target.model_id != current.model_id:
            raise VisionConflict("The previous production model is no longer available")
        try:
            path = self.storage.resolve_uri(target.weights_uri)
        except VisionStorageError as exc:
            raise VisionConflict("The rollback artifact is unavailable") from exc
        if not path.is_file():
            raise VisionConflict("The rollback artifact is unavailable")
        checksum = await run_blocking(
            lambda value: hashlib.sha256(value.read_bytes()).hexdigest(),
            path,
            boundary="filesystem",
            operation="verify_rollback_model_checksum",
            timeout_s=120,
        )
        if checksum != target.checksum:
            raise VisionConflict("The rollback artifact checksum does not match")
        return await self.deploy_model(
            db,
            previous_id,
            user,
            reason=reason or f"Rollback from {current.id}",
            action="rollback",
        )

    async def get_evaluation(
        self, db: AsyncSession, version_id: str, user: User
    ) -> ModelEvaluationOut:
        version = await VisionRepository(db).get_model_version(version_id, user)
        if version is None:
            raise VisionNotFound("Model version not found")
        dataset = await db.get(DatasetVersion, version.dataset_id)
        run = version.training_run
        if dataset is None:
            raise VisionNotFound("Training dataset not found")
        summary = version.metrics.get("summary", {})
        per_class = version.metrics.get("per_class", [])
        confusion_matrix = version.metrics.get("confusion_matrix")
        labels = version.metrics.get("confusion_matrix_labels", [])
        return ModelEvaluationOut(
            model_version_id=version.id,
            model_name=version.model.name,
            version=version.version,
            state="completed",
            metrics=version.metrics,
            summary=summary if isinstance(summary, dict) else {},
            per_class=per_class if isinstance(per_class, list) else [],
            confusion_matrix=confusion_matrix if isinstance(confusion_matrix, list) else None,
            confusion_matrix_labels=labels if isinstance(labels, list) else [],
            dataset_id=dataset.id,
            dataset_version=dataset.version,
            dataset_image_count=dataset.image_count,
            test_image_count=dataset.test_count,
            dataset_checksum=dataset.manifest_checksum,
            split="test",
            image_size=run.image_size,
            base_model=run.base_model,
            preset=run.preset,
            training_date=run.finished_at or run.created_at,
            evaluated_at=run.finished_at or run.created_at,
            artifacts=[
                {
                    "name": name,
                    "url": (
                        f"/vision/model-versions/{version.id}/"
                        f"evaluation-artifacts/{name}"
                    ),
                    "media_type": (
                        "image/jpeg" if name.startswith("val_batch") else "image/png"
                    ),
                }
                for name in sorted(version.evaluation_artifacts)
            ],
        )

    async def resolve_evaluation_artifact(
        self, db: AsyncSession, version_id: str, name: str, user: User
    ) -> Path:
        version = await VisionRepository(db).get_model_version(version_id, user)
        if version is None:
            raise VisionNotFound("Model version not found")
        uri = version.evaluation_artifacts.get(name)
        if not uri:
            raise VisionNotFound("Evaluation artifact not found")
        path = self.storage.resolve_uri(uri)
        if not path.is_file():
            raise VisionNotFound("Evaluation artifact not found")
        return path

    async def resolve_registered_weights(
        self,
        db: AsyncSession,
        version_id: str,
        *,
        org_id: int | None,
        user_id: int | None = None,
        require_production: bool = True,
    ) -> tuple[Path, ModelVersion]:
        version = await VisionRepository(db).get_model_version_for_scope(
            version_id, org_id=org_id, user_id=user_id
        )
        if version is None or (require_production and version.status != "production"):
            raise VisionNotFound("Registered model version is not available")
        try:
            path = self.storage.resolve_uri(version.weights_uri)
        except VisionStorageError as exc:
            raise VisionNotFound("Registered model artifact is unavailable") from exc
        if not path.is_file():
            raise VisionNotFound("Registered model artifact is unavailable")
        checksum = await run_blocking(
            lambda value: hashlib.sha256(value.read_bytes()).hexdigest(),
            path,
            boundary="filesystem",
            operation="verify_registered_model_checksum",
            timeout_s=120,
        )
        if checksum != version.checksum:
            raise VisionConflict("Registered model artifact checksum does not match")
        return path, version
