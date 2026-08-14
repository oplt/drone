from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database.base import Base
from backend.modules.agriculture import analysis_orchestration as orchestration_module
from backend.modules.agriculture import api as agriculture_api
from backend.modules.agriculture import field_context, governance_api
from backend.modules.agriculture.analysis_orchestration import (
    AgricultureAnalysisOrchestration,
)
from backend.modules.agriculture.api import _parse_spatial_bbox
from backend.modules.agriculture.capabilities import (
    CAPABILITIES,
    AgricultureCapabilityReleaseService,
    scope_key,
    validate_capability_ids,
)
from backend.modules.agriculture.inference_profiles import resolve_inference_profile
from backend.modules.agriculture.models import (
    AgricultureAnalysisVideoJob,
    AgricultureCapabilityRelease,
)
from backend.modules.agriculture.p5_models import AgricultureExportJob
from backend.modules.agriculture.quality import telemetry_quality_summary
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.routers import common as agriculture_api_common
from backend.modules.agriculture.routers import exports as agriculture_exports_api
from backend.modules.agriculture.schemas import (
    AnalysisRunIn,
    ExportIn,
    FrameManifestIn,
    ResumableUploadIn,
    TelemetryBatchIn,
)
from backend.modules.video_analysis.contracts import VideoJobRef, VideoSourceRef
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.vision_models.contracts import VisionModelRelease
from backend.modules.vision_models.models import (
    ModelVersion,
    VisionClass,
    VisionModel,
    VisionProject,
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_readiness_catalog_handles_quality_without_a_model_and_explains_blocks(
    monkeypatch,
):
    source = VideoSourceRef(
        id="video-1",
        mission_id="mission-1",
        field_id=10,
        org_id=7,
        status="uploaded",
        fps=30.0,
        created_at=datetime.now(UTC),
    )

    async def list_sources(*_args, **_kwargs):
        return [source]

    async def no_releases(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(
        orchestration_module.video_analysis_port,
        "list_mission_sources",
        list_sources,
    )
    monkeypatch.setattr(
        orchestration_module.agriculture_capability_release_service,
        "active_release_snapshots",
        no_releases,
    )
    flight = SimpleNamespace(
        id="flight-1",
        mission_id="mission-1",
        org_id=7,
        status="captured",
        profile_snapshot={
            "sensor_inventory": ["rgb"],
            "crop_type": "tomato",
            "target_gsd_cm": 2.0,
        },
    )
    result = await AgricultureAnalysisOrchestration().readiness(
        SimpleNamespace(),
        flight=flight,
        user=SimpleNamespace(id=3),
    )
    by_id = {item["id"]: item for item in result["capabilities"]}

    assert set(CAPABILITIES) >= {"quality", "coverage", "weed_detection"}
    assert by_id["quality"]["available"] is True
    assert by_id["coverage"]["available"] is True
    assert by_id["weed_detection"]["available"] is False
    assert "No production Vision model" in by_id["weed_detection"][
        "unavailable_reasons"
    ][0]
    assert all(item["satisfied"] for item in result["capture_prerequisites"])


def test_capability_boundary_rejects_legacy_aliases_instead_of_remapping():
    assert validate_capability_ids(["quality", "weed_detection"]) == [
        "quality",
        "weed_detection",
    ]
    with pytest.raises(ValueError, match="Retired analysis capability names"):
        validate_capability_ids(["weed"])
    with pytest.raises(ValueError, match="Unknown analysis capabilities"):
        validate_capability_ids(["future_magic"])


@pytest.mark.asyncio
async def test_capability_release_references_vision_without_copying_artifact_ownership():
    version = VisionModelRelease(
        version_id="version-1",
        status="production",
        model_id="model-1",
        model_name="weed detector",
        model_version=1,
        model_checksum="a" * 64,
        dataset_id="dataset-1",
        crop="tomato",
        classes=("weed",),
        evaluation_metrics={},
        capability_id="weed_detection",
        project_org_id=7,
        project_created_by_user_id=3,
    )

    class Database:
        added = []

        async def scalar(self, _statement):
            return None

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            return None

    db = Database()
    release = await AgricultureCapabilityReleaseService().activate_for_model_version(
        db,
        version=version,
        org_id=7,
        user_id=3,
    )

    assert release.scope_key == scope_key(org_id=7, user_id=3)
    assert release.vision_model_version_id == "version-1"
    assert release.capability_id == "weed_detection"
    assert release.crop_types == ["tomato"]
    assert not hasattr(release, "artifact_uri")
    assert not hasattr(release, "checksum")


@pytest.mark.asyncio
async def test_active_capability_release_lookup_executes_against_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[
                    VisionProject.__table__,
                    VisionClass.__table__,
                    VisionModel.__table__,
                    ModelVersion.__table__,
                    AgricultureCapabilityRelease.__table__,
                ],
            )
        )
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    try:
        async with session_factory() as db:
            project = VisionProject(
                id="project-release-lookup",
                org_id=7,
                created_by_user_id=3,
                name="Weed project",
                crop="tomato",
                capability_id="weed_detection",
                task_type="detection",
                status="active",
            )
            model = VisionModel(
                id="model-release-lookup",
                org_id=7,
                project_id=project.id,
                name="Weed detector",
                crop="tomato",
                task_type="detection",
            )
            version = ModelVersion(
                id="version-release-lookup",
                model_id=model.id,
                training_run_id="training-release-lookup",
                dataset_id="dataset-release-lookup",
                version=1,
                architecture="yolo26n.pt",
                weights_uri="vision://projects/project-release-lookup/models/v1/best.pt",
                classes=["weed"],
                metrics={"map50": 0.7},
                evaluation_artifacts={},
                checksum="a" * 64,
                status="production",
            )
            release = AgricultureCapabilityRelease(
                id="release-lookup",
                scope_key=scope_key(org_id=7, user_id=3),
                org_id=7,
                created_by_user_id=3,
                approved_by_user_id=3,
                capability_id="weed_detection",
                vision_model_version_id=version.id,
                status="active",
                sensor_type="rgb",
                crop_types=["tomato"],
                inference_profile={"confidence_threshold": 0.35},
                thresholds={},
            )
            other_project = VisionProject(
                id="project-release-other-org",
                org_id=8,
                created_by_user_id=4,
                name="Other weed project",
                crop="corn",
                capability_id="weed_detection",
                task_type="detection",
                status="active",
            )
            other_model = VisionModel(
                id="model-release-other-org",
                org_id=8,
                project_id=other_project.id,
                name="Other weed detector",
                crop="corn",
                task_type="detection",
            )
            other_version = ModelVersion(
                id="version-release-other-org",
                model_id=other_model.id,
                training_run_id="training-release-other-org",
                dataset_id="dataset-release-other-org",
                version=1,
                architecture="yolo26n.pt",
                weights_uri="vision://projects/project-release-other-org/models/v1/best.pt",
                classes=["weed"],
                metrics={"map50": 0.8},
                evaluation_artifacts={},
                checksum="b" * 64,
                status="production",
            )
            other_release = AgricultureCapabilityRelease(
                id="release-other-org",
                scope_key=scope_key(org_id=8, user_id=4),
                org_id=8,
                created_by_user_id=4,
                approved_by_user_id=4,
                capability_id="weed_detection",
                vision_model_version_id=other_version.id,
                status="active",
                sensor_type="rgb",
                crop_types=["corn"],
                inference_profile={"confidence_threshold": 0.5},
                thresholds={},
            )
            db.add_all(
                [
                    project,
                    model,
                    version,
                    release,
                    other_project,
                    other_model,
                    other_version,
                    other_release,
                ]
            )
            await db.commit()

            snapshots = await AgricultureCapabilityReleaseService().active_release_snapshots(
                db,
                org_id=7,
                user_id=3,
                capability_ids=["weed_detection"],
            )

            assert snapshots["weed_detection"]["release_id"] == release.id
            assert snapshots["weed_detection"]["vision_model_version_id"] == version.id
            assert snapshots["weed_detection"]["model_checksum"] == "a" * 64
            profile = snapshots["weed_detection"]["inference_profile"]
            assert profile["capability_id"] == "weed_detection"
            assert profile["confidence_threshold"] == 0.35
            assert profile["profile_version"] == "agriculture-inference-profile.v1"
            assert len(profile["profile_digest"]) == 64
            assert all(
                snapshot["vision_model_version_id"] != other_version.id
                for snapshot in snapshots.values()
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_orchestration_reuses_only_an_exact_completed_inference_contract(
    monkeypatch,
):
    snapshot = {
        "release_id": "release-1",
        "vision_model_version_id": "version-1",
        "model_checksum": "a" * 64,
        "inference_profile": resolve_inference_profile("weed_detection"),
    }
    candidate = AgricultureAnalysisVideoJob(
        id="link-old",
        run_id="run-old",
        capability_id="weed_detection",
        capability_release_id="release-1",
        video_id="video-1",
        video_job_id="job-old",
        inference_snapshot={
            **snapshot,
            "source_checksum": "b" * 64,
            "resolved_model_version": f"registered:version-1:{'a' * 64}",
            "telemetry_match_version": "nearest-telemetry.v1",
            "capability_contract_version": "agriculture-capabilities.v1",
        },
        created_at=datetime.now(UTC),
    )
    completed_job = VideoJobRef(
        id="job-old",
        video_id="video-1",
        status="completed",
        model_version_id="version-1",
        model_version=f"registered:version-1:{'a' * 64}",
        source_checksum="b" * 64,
        progress=100.0,
        error=None,
        terminal_reason_code="COMPLETED",
        inference_profile=snapshot["inference_profile"],
    )
    source = VideoSourceRef(
        id="video-1",
        mission_id="mission-1",
        field_id=10,
        org_id=7,
        status="analyzed",
        fps=30.0,
        created_at=datetime.now(UTC),
    )
    stage = SimpleNamespace(status="queued", progress=0.0, metrics={})

    class Database:
        def __init__(self):
            self.scalar_results = [[], [candidate]]
            self.added = []

        async def scalars(self, _statement):
            return _Rows(self.scalar_results.pop(0))

        async def scalar(self, _statement):
            return stage

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            return None

    async def list_sources(*_args, **_kwargs):
        return [source]

    async def list_jobs(*_args, **_kwargs):
        return [completed_job]

    async def unexpected_start(*_args, **_kwargs):
        raise AssertionError("an exact completed job should have been reused")

    monkeypatch.setattr(
        orchestration_module.video_analysis_port,
        "list_mission_sources",
        list_sources,
    )
    monkeypatch.setattr(
        orchestration_module.video_analysis_port, "list_jobs", list_jobs
    )
    monkeypatch.setattr(
        orchestration_module.video_analysis_port,
        "start_or_reuse_job",
        unexpected_start,
    )
    db = Database()
    links = await AgricultureAnalysisOrchestration().ensure_video_jobs(
        db,
        run=SimpleNamespace(
            id="run-new",
            retry_count=0,
            model_versions={"weed_detection": snapshot},
        ),
        flight=SimpleNamespace(mission_id="mission-1", org_id=7),
        user=SimpleNamespace(id=3),
    )

    assert links[0].video_job_id == "job-old"
    assert links[0].inference_snapshot["reused_completed_job"] is True
    assert links[0].inference_snapshot["reused_from_run_id"] == "run-old"


@pytest.mark.asyncio
async def test_orchestration_fails_run_when_one_required_video_job_fails(monkeypatch):
    link_ok = SimpleNamespace(
        video_job_id="job-ok",
        inference_snapshot={},
    )
    link_failed = SimpleNamespace(
        video_job_id="job-failed",
        inference_snapshot={},
    )
    stage = SimpleNamespace(
        status="queued",
        progress=0.0,
        metrics={},
        error=None,
        finished_at=None,
    )
    run = SimpleNamespace(
        id="run-1",
        model_versions={"weed_detection": {"version_id": "version-1"}},
        requested_by_user_id=3,
        status="running",
        error=None,
        finished_at=None,
        audit_json={},
        progress=10.0,
    )

    async def list_jobs(*_args, **_kwargs):
        return [
            VideoJobRef(
                id="job-ok",
                video_id="video-1",
                status="completed",
                model_version_id="version-1",
                model_version="registered:version-1:checksum",
                source_checksum="a" * 64,
                progress=100.0,
                error=None,
                terminal_reason_code="COMPLETED",
            ),
            VideoJobRef(
                id="job-failed",
                video_id="video-2",
                status="failed",
                model_version_id="version-1",
                model_version="registered:version-1:checksum",
                source_checksum=None,
                progress=20.0,
                error="inference failed",
                terminal_reason_code="INFERENCE_FAILED",
            ),
        ]

    monkeypatch.setattr(
        orchestration_module.video_analysis_port,
        "list_jobs",
        list_jobs,
    )

    class Database:
        committed = False

        async def scalars(self, _statement):
            return _Rows([link_ok, link_failed])

        async def scalar(self, _statement):
            return stage

        async def commit(self):
            self.committed = True

    db = Database()
    state, job_ids = await AgricultureAnalysisOrchestration().prerequisite_state(
        db,
        run=run,
        flight=SimpleNamespace(org_id=7),
    )

    assert state == "failed"
    assert job_ids == ["job-failed", "job-ok"]
    assert run.status == "failed"
    assert stage.status == "failed"
    assert stage.metrics["failed_job_ids"] == ["job-failed"]
    assert stage.metrics["terminal_reasons"] == {
        "job-failed": "INFERENCE_FAILED"
    }
    assert db.committed is True


def test_missing_telemetry_is_an_explicit_blocked_quality_result():
    assert telemetry_quality_summary([]) == {
        "status": "blocked",
        "reason": "telemetry_missing",
        "sample_count": 0,
    }


@pytest.mark.asyncio
async def test_spatial_viewport_filters_and_counts_before_pagination():
    statements = []

    class Database:
        async def scalar(self, statement):
            statements.append(statement)
            return 17

        async def scalars(self, statement):
            statements.append(statement)
            return _Rows([])

    rows, total = await agriculture_repository.list_spatial_observations(
        Database(),
        run_id="run-1",
        user=SimpleNamespace(org_id=7),
        bbox=(4.0, 50.0, 4.2, 50.2),
        observation_type="weed",
        min_severity=0.4,
        min_confidence=0.5,
        offset=200,
        limit=100,
    )
    count_sql = str(
        statements[0].compile(dialect=postgresql.dialect())
    ).lower()
    page_sql = str(statements[1].compile(dialect=postgresql.dialect())).lower()

    assert rows == [] and total == 17
    assert "st_intersects" in count_sql
    assert "st_makeenvelope" in count_sql
    assert "agriculture_flights.org_id" in count_sql
    assert "agriculture_observations.run_id" in count_sql
    assert " limit " not in count_sql
    assert " limit " in page_sql and " offset " in page_sql


def test_spatial_bbox_contract_rejects_antimeridian_and_invalid_extents():
    assert _parse_spatial_bbox("4,50,4.2,50.2") == (4.0, 50.0, 4.2, 50.2)
    with pytest.raises(HTTPException):
        _parse_spatial_bbox("170,-10,-170,10")
    with pytest.raises(HTTPException):
        _parse_spatial_bbox("4,50,4,50.2")


@pytest.mark.asyncio
async def test_old_video_attempt_cannot_complete_a_newer_claim():
    current = SimpleNamespace(id="job-1", status="running", attempt=2)

    class Database:
        rolled_back = False

        async def scalar(self, _statement):
            return current

        async def rollback(self):
            self.rolled_back = True

    db = Database()
    completed = await VideoAnalysisRepository(db).mark_job_completed(
        SimpleNamespace(id="job-1"), expected_attempt=1
    )

    assert completed is False
    assert current.status == "running"
    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_cancelled_video_job_cannot_be_completed_by_inflight_worker():
    current = SimpleNamespace(id="job-1", status="cancelled", attempt=1)

    class Database:
        rolled_back = False

        async def scalar(self, _statement):
            return current

        async def rollback(self):
            self.rolled_back = True

    db = Database()
    completed = await VideoAnalysisRepository(db).mark_job_completed(
        SimpleNamespace(id="job-1"),
        expected_attempt=1,
    )

    assert completed is False
    assert current.status == "cancelled"
    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_duplicate_worker_attempt_cannot_flush_detections():
    class Result:
        rowcount = 0

    class Database:
        rolled_back = False
        committed = False

        def add_all(self, _values):
            return None

        async def execute(self, _statement):
            return Result()

        async def rollback(self):
            self.rolled_back = True

        async def commit(self):
            self.committed = True

    db = Database()
    persisted = await VideoAnalysisRepository(db).flush_batch(
        [],
        job=SimpleNamespace(id="job-1", heartbeat_at=None),
        progress=50,
        expected_attempt=1,
    )

    assert persisted is False
    assert db.rolled_back is True
    assert db.committed is False


def test_p0_migration_preserves_legacy_rows_and_adds_reversible_contracts():
    migration = (
        Path(__file__).resolve().parents[1]
        / "infrastructure/persistence/alembic/versions/"
        "d7e8f9g0h1i2_p0_safe_analysis_slice.py"
    ).read_text()

    assert "migration_state = 'quarantined'" in migration
    assert "linked_capability_release_id" in migration
    assert "uq_agri_active_capability_release" in migration
    assert "uq_agri_stage_execution_key" in migration
    assert "annotation_revision" in migration
    assert "agriculture_analysis_video_jobs" in migration
    assert 'op.drop_table("agriculture_capability_releases")' in migration


@pytest.mark.asyncio
async def test_repaired_upload_telemetry_and_field_zone_paths_execute(
    monkeypatch,
):
    flight = SimpleNamespace(
        id="flight-1",
        mission_id="mission-1",
        field_id=10,
        org_id=7,
        status="captured",
        input_manifest={},
        coverage_summary={},
    )
    org_user = SimpleNamespace(
        org_id=7,
        user=SimpleNamespace(id=3, org_id=7),
    )

    async def owned_flight(*_args, **_kwargs):
        return flight

    async def no_rate_limit(**_kwargs):
        return None

    async def no_telemetry(*_args, **_kwargs):
        return 0, 0, 0, 0

    class Database:
        def __init__(self):
            self.added = []

        async def scalar(self, _statement):
            self._scalar_calls = getattr(self, "_scalar_calls", 0) + 1
            if self._scalar_calls in {1, 3}:
                return None
            return flight

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            return None

        async def refresh(self, value):
            if not getattr(value, "created_at", None):
                value.created_at = datetime.now(UTC)

    db = Database()
    monkeypatch.setattr(agriculture_api_common, "_owned_flight", owned_flight)
    monkeypatch.setattr(agriculture_api_common, "enforce_rate_limit", no_rate_limit)
    monkeypatch.setattr(
        agriculture_api.agriculture_service, "ingest_telemetry", no_telemetry
    )
    monkeypatch.setattr(
        agriculture_api.agriculture_storage, "usage_bytes", lambda _prefix: 0
    )
    monkeypatch.setattr(
        agriculture_api.agriculture_storage,
        "validate_tenant_key",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        agriculture_api.agriculture_storage,
        "validate_content",
        lambda **_kwargs: None,
    )

    upload = await agriculture_api.initiate_upload(
        "flight-1",
        ResumableUploadIn(
            source_kind="rgb_video",
            filename="capture.mp4",
            content_type="video/mp4",
            total_bytes=1024,
            checksum="a" * 64,
        ),
        db,
        org_user,
    )
    telemetry = await agriculture_api.ingest_telemetry(
        "flight-1",
        TelemetryBatchIn(
            samples=[
                {
                    "timestamp": datetime.now(UTC),
                    "lat": 50.85,
                    "lon": 4.35,
                }
            ]
        ),
        "telemetry-batch-1",
        db,
        org_user,
    )

    assert upload["chunk_bytes"] == agriculture_api.settings.agriculture_upload_chunk_bytes
    assert telemetry.inserted == 0

    boundary = SimpleNamespace(
        revision=2,
        boundary_json={
            "type": "Polygon",
            "coordinates": [
                [[4.0, 50.0], [4.2, 50.0], [4.2, 50.2], [4.0, 50.2], [4.0, 50.0]]
            ],
        },
    )

    async def owned_field(*_args, **_kwargs):
        return SimpleNamespace(id=10)

    db.scalar = lambda _statement: _async_value(boundary)
    monkeypatch.setattr(field_context, "_owned", owned_field)
    result = await field_context.add_agriculture_zone(
        10,
        field_context.ZoneIn(
            zone_type="exclusion",
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [[4.05, 50.05], [4.1, 50.05], [4.1, 50.1], [4.05, 50.1], [4.05, 50.05]]
                ],
            },
            name="Wet corner",
        ),
        db,
        org_user,
    )
    assert result["id"]


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_repaired_media_advisory_manifest_analysis_and_export_routes_execute(
    monkeypatch,
):
    flight = SimpleNamespace(
        id="flight-1",
        mission_id="mission-1",
        field_id=10,
        org_id=7,
        status="captured",
        input_manifest={},
        profile_snapshot={"sensor_inventory": ["rgb"]},
    )
    user = SimpleNamespace(id=3, org_id=7)
    org_user = SimpleNamespace(org_id=7, user=user)

    async def owned_flight(*_args, **_kwargs):
        return flight

    async def no_rate_limit(**_kwargs):
        return None

    monkeypatch.setattr(agriculture_api_common, "_owned_flight", owned_flight)
    monkeypatch.setattr(agriculture_api_common, "enforce_rate_limit", no_rate_limit)

    class InventoryDatabase:
        async def scalars(self, _statement):
            return _Rows([])

        async def scalar(self, _statement):
            return 0

    monkeypatch.setattr(
        agriculture_api.agriculture_storage, "usage_bytes", lambda _prefix: 0
    )
    inventory = await agriculture_api.get_media_inventory(
        flight.id, InventoryDatabase(), org_user
    )
    assert inventory["storage_quota_bytes"] == (
        agriculture_api.settings.agriculture_org_storage_quota_bytes
    )

    class FrameUpload:
        async def read(self):
            return b"encoded-frame"

    processor = SimpleNamespace(
        sampler_hz=3.0,
        dropped_frames=0,
        submit=lambda _frame: None,
        process_one=lambda _callback: SimpleNamespace(
            frame_index=30,
            timestamp_seconds=1.0,
            state="clear",
            alerts=[],
            geolocation=None,
            expires_at=2.0,
        ),
    )
    agriculture_api._live_processors.clear()
    monkeypatch.setattr(agriculture_api_common, "decode_rgb_frame", lambda _data: object())
    monkeypatch.setattr(
        agriculture_api_common, "LiveAgricultureProcessor", lambda **_kwargs: processor
    )
    advisory = await agriculture_api.live_advisory(
        flight.id,
        FrameUpload(),
        1.0,
        None,
        None,
        flight,
    )
    assert advisory.state == "clear"

    async def create_frame_manifest(*_args, **_kwargs):
        return {"flight_id": flight.id, "inserted": 1}

    monkeypatch.setattr(
        agriculture_api.agriculture_service,
        "create_frame_manifest",
        create_frame_manifest,
    )
    manifest = await agriculture_api.register_frame_manifest(
        flight.id,
        FrameManifestIn(
            media_id="media-1",
            source_checksum="a" * 64,
            frames=[{"frame_index": 0, "timestamp": datetime.now(UTC)}],
        ),
        SimpleNamespace(),
        org_user,
    )
    assert manifest["inserted"] == 1

    run = SimpleNamespace(
        id="run-1",
        flight_id=flight.id,
        audit_json={},
        status="queued",
        input_checksum="b" * 64,
        progress=0.0,
        retry_count=0,
        model_versions={},
        analysis_profile={},
        baseline_flight_id=None,
        requested_by_user_id=user.id,
        error=None,
        finished_at=None,
    )

    async def no_existing(*_args, **_kwargs):
        return None

    async def ready_request(*_args, **_kwargs):
        return ["quality"], {}, {"catalog_version": "agriculture-capabilities.v1"}

    async def transition(*_args, **_kwargs):
        flight.status = "processing"

    async def create_run(*_args, **_kwargs):
        return run

    async def ensure_jobs(*_args, **_kwargs):
        return []

    async def ready_inventory(*_args, **_kwargs):
        return {"ready_for_processing": True}

    class RouteDatabase:
        def add(self, value):
            if isinstance(value, AgricultureExportJob):
                value.id = value.id or "export-1"

        async def scalar(self, _statement):
            return 0

        async def scalars(self, _statement):
            return _Rows([])

        async def commit(self):
            return None

        async def flush(self):
            return None

        async def refresh(self, _value):
            return None

    db = RouteDatabase()
    monkeypatch.setattr(agriculture_api_common, "_media_inventory", ready_inventory)
    monkeypatch.setattr(
        agriculture_api.agriculture_repository, "get_run_by_key", no_existing
    )
    monkeypatch.setattr(
        agriculture_api.agriculture_analysis_orchestration,
        "resolve_request",
        ready_request,
    )
    monkeypatch.setattr(
        agriculture_api.agriculture_analysis_orchestration,
        "ensure_video_jobs",
        ensure_jobs,
    )
    monkeypatch.setattr(
        agriculture_api.agriculture_service, "transition_flight", transition
    )
    monkeypatch.setattr(
        agriculture_api.agriculture_service, "create_analysis_run", create_run
    )
    monkeypatch.setattr(agriculture_api_common, "emit_audit_event", lambda **_kwargs: None)
    created = await agriculture_api.create_analysis_run(
        flight.id,
        AnalysisRunIn(idempotency_key="analysis-key-1", requested_analyses=["quality"]),
        db,
        org_user,
    )
    assert created.id == run.id
    assert run.audit_json["readiness"]["catalog_version"].endswith(".v1")

    async def get_run(*_args, **_kwargs):
        return run

    monkeypatch.setattr(agriculture_api.agriculture_repository, "get_run", get_run)
    monkeypatch.setattr(
        agriculture_exports_api.agriculture_analysis_queue,
        "enqueue_stage",
        lambda **_kwargs: "task-export-1",
    )
    exported = await agriculture_api.create_agriculture_export(
        run.id,
        ExportIn(artifact_kind="observations", format="geojson"),
        db,
        org_user,
    )
    assert exported.id == "export-1"
    assert exported.status == "queued"


@pytest.mark.asyncio
async def test_capability_release_activation_retires_prior_active_release():
    first = VisionModelRelease(
        version_id="version-1",
        status="production",
        model_id="model-1",
        model_name="weed detector",
        model_version=1,
        model_checksum="a" * 64,
        dataset_id="dataset-1",
        crop="tomato",
        classes=("weed",),
        evaluation_metrics={},
        capability_id="weed_detection",
        project_org_id=7,
        project_created_by_user_id=3,
    )
    second = VisionModelRelease(
        version_id="version-2",
        status="production",
        model_id="model-1",
        model_name="weed detector",
        model_version=2,
        model_checksum="b" * 64,
        dataset_id="dataset-1",
        crop="tomato",
        classes=("weed",),
        evaluation_metrics={},
        capability_id="weed_detection",
        project_org_id=7,
        project_created_by_user_id=3,
    )
    existing = AgricultureCapabilityRelease(
        id="release-old",
        scope_key=scope_key(org_id=7, user_id=3),
        org_id=7,
        created_by_user_id=3,
        approved_by_user_id=3,
        capability_id="weed_detection",
        vision_model_version_id="version-1",
        status="active",
        sensor_type="rgb",
        crop_types=["tomato"],
        inference_profile={},
        thresholds={},
    )

    class Database:
        def __init__(self):
            self.added = []
            self._existing = existing

        async def scalar(self, _statement):
            return self._existing

        def add(self, value):
            self.added.append(value)
            self._existing = value

        async def flush(self):
            return None

    service = AgricultureCapabilityReleaseService()
    db = Database()
    first_release = await service.activate_for_model_version(
        db, version=first, org_id=7, user_id=3
    )
    assert first_release.vision_model_version_id == "version-1"
    assert first_release.status == "active"

    replacement = await service.activate_for_model_version(
        db, version=second, org_id=7, user_id=3
    )
    assert existing.status == "retired"
    assert existing.retired_at is not None
    assert replacement.vision_model_version_id == "version-2"
    assert replacement.status == "active"
    assert any(
        isinstance(item, AgricultureCapabilityRelease)
        and item.vision_model_version_id == "version-2"
        for item in db.added
    )


def test_legacy_model_publish_endpoints_are_gone_after_capability_contract():
    with pytest.raises(HTTPException) as blocked:
        governance_api._legacy_registry_read_only()
    assert blocked.value.status_code == 410
    assert blocked.value.detail["code"] == "LEGACY_MODEL_REGISTRY_READ_ONLY"


@pytest.mark.asyncio
async def test_stale_video_lease_reconciliation_fails_job_and_video():
    now = datetime.now(UTC)
    job = SimpleNamespace(
        id="job-stale",
        video_id="video-1",
        status="running",
        error=None,
        finished_at=None,
        heartbeat_at=now,
        lease_expires_at=now,
        terminal_reason_code=None,
        terminal_stage=None,
    )
    video = SimpleNamespace(id="video-1", status="analyzing")

    class Database:
        committed = False
        rolled_back = False

        async def scalars(self, statement):
            sql = str(statement).lower()
            if "video_analysis_jobs" in sql:
                return _Rows([job])
            return _Rows([video])

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    db = Database()
    reconciled = await VideoAnalysisRepository(db).reconcile_stale_jobs(limit=10)

    assert reconciled == 1
    assert job.status == "failed"
    assert job.terminal_reason_code == "WORKER_LEASE_EXPIRED"
    assert job.terminal_stage == "worker_lease"
    assert video.status == "analysis_failed"
    assert db.committed is True


def test_agriculture_undefined_name_guard_stays_clean():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "F821,F401",
            "backend/modules/agriculture",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
