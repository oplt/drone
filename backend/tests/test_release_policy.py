from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.modules.identity.models import UserRole
from backend.modules.agriculture.capabilities import (
    AgricultureCapabilityReleaseService,
    default_inference_profile,
)
from backend.modules.vision_models import training_operations
from backend.modules.vision_models.application import VisionApplication
from backend.modules.vision_models.contracts import VisionModelRelease
from backend.modules.vision_models.release_policy import (
    POLICY_VERSION,
    evaluate_release,
)


def _base_kwargs(**overrides):
    values = {
        "status": "candidate",
        "metrics": {"summary": {"map50": 0.8, "precision": 0.7, "recall": 0.6}},
        "weights_uri": "vision://weights.pt",
        "checksum": "a" * 64,
        "capability_id": "object_detection",
        "minimum_map50": 0.25,
        "training_run_id": "run-1",
        "dataset_id": "dataset-1",
        "dataset_version": 1,
        "dataset_manifest_checksum": "b" * 64,
        "test_count": 4,
        "artifact_verified": True,
        "task_type": "detection",
        "classes": ["weed"],
    }
    values.update(overrides)
    return values


def test_evaluate_release_success_freezes_inference_contract():
    result = evaluate_release(**_base_kwargs())
    assert result.eligible
    assert result.reasons == ()
    assert result.policy_version == POLICY_VERSION
    assert result.inference_contract["capability_id"] == "object_detection"
    assert result.inference_contract["classes"] == ["weed"]
    assert result.inference_contract["model_checksum"] == "a" * 64
    assert result.inference_contract["dataset_checksum"] == "b" * 64
    assert result.inference_contract["evaluation_metrics"]["map50"] == 0.8
    assert result.inference_contract["confidence_threshold"] == 0.35
    assert result.inference_contract["frame_stride_seconds"] == 1.0
    assert result.inference_contract["small_object_mode"] is False
    assert result.inference_contract["tracking_enabled"] is False
    assert result.inference_contract["tracker_type"] == "bytetrack"


def test_evaluate_release_freezes_explicit_inference_profile():
    result = evaluate_release(
        **_base_kwargs(
            confidence_threshold=0.55,
            frame_stride_seconds=0.25,
            small_object_mode=True,
            tracking_enabled=True,
            tracker_type="botsort",
        )
    )
    assert result.inference_contract["confidence_threshold"] == 0.55
    assert result.inference_contract["frame_stride_seconds"] == 0.25
    assert result.inference_contract["small_object_mode"] is True
    assert result.inference_contract["tracking_enabled"] is True
    assert result.inference_contract["tracker_type"] == "botsort"


@pytest.mark.parametrize(
    ("capability_id", "map50", "recall", "eligible"),
    [
        ("stand_count", 0.30, 0.50, True),
        ("stand_count", 0.30, 0.49, False),
        ("weed_detection", 0.34, 0.80, False),
        ("crop_health", 0.27, 0.80, False),
        ("object_detection", 0.30, 0.10, True),
    ],
)
def test_capability_metric_floors(capability_id, map50, recall, eligible):
    result = evaluate_release(
        **_base_kwargs(
            capability_id=capability_id,
            metrics={"summary": {"map50": map50, "recall": recall}},
        )
    )
    assert result.eligible is eligible


@pytest.mark.asyncio
async def test_capability_activation_prefers_frozen_profile():
    frozen_profile = {
        "confidence_threshold": 0.6,
        "frame_stride_seconds": 0.5,
        "small_object_mode": True,
        "tracking_enabled": True,
        "tracker_type": "botsort",
    }
    version = VisionModelRelease(
        version_id="version-1",
        status="production",
        model_id="model-1",
        model_name="detector",
        model_version=1,
        model_checksum="a" * 64,
        dataset_id="dataset-1",
        crop="wheat",
        classes=("weed",),
        evaluation_metrics={
            "deployment_audit": [{"inference_contract": frozen_profile}]
        },
        capability_id="object_detection",
        project_org_id=7,
        project_created_by_user_id=9,
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        add=Mock(),
        flush=AsyncMock(),
    )
    release = await AgricultureCapabilityReleaseService().activate_for_model_version(
        db, version=version, org_id=7, user_id=9
    )
    assert release.inference_profile == frozen_profile
    assert release.inference_profile != default_inference_profile("object_detection")


def test_evaluate_release_blocks_low_map50():
    result = evaluate_release(**_base_kwargs(metrics={"summary": {"map50": 0.1}}))
    assert not result.eligible
    assert any("map50" in reason for reason in result.reasons)


def test_evaluate_release_blocks_missing_evaluation():
    result = evaluate_release(**_base_kwargs(metrics={}))
    assert not result.eligible
    assert any("evaluation result" in reason for reason in result.reasons)


def test_evaluate_release_blocks_missing_artifact_verification():
    result = evaluate_release(
        **_base_kwargs(artifact_verified=False, weights_uri="", checksum="")
    )
    assert not result.eligible
    assert any("artifact" in reason for reason in result.reasons)


def test_evaluate_release_blocks_missing_lineage_and_empty_test_set():
    result = evaluate_release(
        **_base_kwargs(
            training_run_id=None,
            dataset_id=None,
            test_count=0,
        )
    )
    assert not result.eligible
    assert any("training run" in reason for reason in result.reasons)
    assert any("dataset lineage" in reason for reason in result.reasons)
    assert any("test set" in reason for reason in result.reasons)


def test_evaluate_release_blocks_regression_against_production():
    result = evaluate_release(
        **_base_kwargs(
            metrics={"summary": {"map50": 0.4}},
            production_map50=0.9,
        )
    )
    assert not result.eligible
    assert any("regression" in reason for reason in result.reasons)


def _candidate_version(*, map50: float = 0.1) -> SimpleNamespace:
    return SimpleNamespace(
        id="version-1",
        model_id="model-1",
        version=2,
        architecture="yolo26s",
        status="candidate",
        training_run_id="run-1",
        dataset_id="dataset-1",
        metrics={"summary": {"map50": map50}, "deployment_audit": []},
        weights_uri="vision://weights.pt",
        checksum="a" * 64,
        classes=["weed"],
        created_at=datetime.now(UTC),
        model=SimpleNamespace(
            id="model-1",
            name="detector",
            crop="wheat",
            task_type="detection",
            project_id="project-1",
            project=SimpleNamespace(
                capability_id="object_detection",
                org_id=7,
                created_by_user_id=9,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_deploy_authorized_override_accepted(monkeypatch):
    version = _candidate_version()

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_model_version(self, version_id, _user, **_kwargs):
            return version if version_id == version.id else None

    async def fake_activate(_db, **_kwargs):
        return None

    monkeypatch.setattr(training_operations, "VisionRepository", FakeRepository)
    monkeypatch.setattr(
        training_operations,
        "agriculture_capability_release_service",
        SimpleNamespace(activate_for_model_version=fake_activate),
    )
    app = VisionApplication()
    monkeypatch.setattr(app, "_verify_weights_checksum", AsyncMock(return_value=False))
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        execute=AsyncMock(return_value=None),
        get=AsyncMock(
            return_value=SimpleNamespace(
                version=1, test_count=3, manifest_checksum="c" * 64
            )
        ),
        commit=AsyncMock(return_value=None),
    )

    result = await app.deploy_model(
        db,
        version.id,
        SimpleNamespace(id=9, org_id=7, role=UserRole.org_admin),
        override=True,
        reason="Authorized emergency hotfix",
    )
    assert result.status == "production"
    audit = version.metrics["deployment_audit"][-1]
    assert audit["override"] is True
    assert audit["failed_checks"]
    assert audit["inference_contract"]["policy_version"] == POLICY_VERSION
    assert audit["actor"] == 9
    assert audit["reason"] == "Authorized emergency hotfix"
    assert audit["previous_production_id"] is None


@pytest.mark.asyncio
async def test_deploy_unauthorized_override_rejected(monkeypatch):
    version = _candidate_version()

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_model_version(self, version_id, _user, **_kwargs):
            return version if version_id == version.id else None

    monkeypatch.setattr(training_operations, "VisionRepository", FakeRepository)

    with pytest.raises(RuntimeError, match="authorized role"):
        await VisionApplication().deploy_model(
            SimpleNamespace(),
            version.id,
            SimpleNamespace(id=1, org_id=7, role=UserRole.viewer),
            override=True,
            reason="I am not allowed",
        )
