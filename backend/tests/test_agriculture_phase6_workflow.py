from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from backend.entrypoints.workers import agriculture_tasks
from backend.modules.agriculture import stage_executor
from backend.modules.agriculture.queue import agriculture_analysis_queue
from backend.modules.agriculture.stage_operations import (
    STAGE_VERSIONS,
    fuse_sensor_results,
    stage_input_checksum,
)
from backend.modules.workflow_events.service import (
    append_workflow_event,
    workflow_event_query,
)


def test_workflow_event_replay_query_is_tenant_or_creator_scoped() -> None:
    org_sql = str(
        workflow_event_query(
            domain="agriculture_analysis",
            stream_id="same-stream",
            org_id=1,
            user_id=999,
            after_id=41,
        ).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    personal_sql = str(
        workflow_event_query(
            domain="agriculture_analysis",
            stream_id="same-stream",
            org_id=None,
            user_id=7,
        ).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "workflow_events.org_id = 1" in org_sql
    assert "workflow_events.user_id = 999" not in org_sql
    assert "workflow_events.org_id IS NULL" in personal_sql
    assert "workflow_events.user_id = 7" in personal_sql
    assert "workflow_events.id > 41" in org_sql


def test_stage_fingerprints_are_stable_and_include_attempt_and_upstream() -> None:
    run = SimpleNamespace(
        input_checksum="source-sha",
        retry_count=2,
        model_versions={"weed_detection": {"model_checksum": "model-sha"}},
        analysis_profile={"preset": "balanced"},
        baseline_flight_id="flight-before",
    )
    first = stage_input_checksum(
        run,
        "geospatial_aggregation",
        upstream_checksum="rgb-output",
        extra={"cluster_radius_m": 8.0},
    )
    reordered = stage_input_checksum(
        run,
        "geospatial_aggregation",
        extra={"cluster_radius_m": 8.0},
        upstream_checksum="rgb-output",
    )
    changed = stage_input_checksum(
        run,
        "geospatial_aggregation",
        upstream_checksum="different-rgb-output",
        extra={"cluster_radius_m": 8.0},
    )
    assert first == reordered
    assert first != changed
    assert len(first) == 64
    assert STAGE_VERSIONS["geospatial_aggregation"].endswith(".v2")


def test_phase6_tasks_own_real_operations_and_process_run_never_self_polls() -> None:
    stage_source = inspect.getsource(stage_executor._run_operation)
    process_source = inspect.getsource(agriculture_tasks.process_agriculture_run)

    assert "aggregate_geospatial_results" in stage_source
    assert "coordinate_rgb_inference" in stage_source
    assert "persist_segmentation_result" in stage_source
    assert "compare_temporal_results" in stage_source
    assert "fuse_sensor_results" in stage_source
    assert "build_export_result" in stage_source
    assert "self.apply_async" not in process_source
    assert "agriculture_inference_poll" not in process_source


def test_each_owned_stage_has_an_independent_queue_and_replay_target() -> None:
    assert set(agriculture_analysis_queue.STAGE_TASKS) == {
        "rgb_inference",
        "geospatial_aggregation",
        "segmentation",
        "temporal_comparison",
        "sensor_fusion",
        "exports",
    }
    assert (
        len({queue_setting for _, queue_setting in agriculture_analysis_queue.STAGE_TASKS.values()})
        == 6
    )


def test_concurrent_duplicate_event_reuses_the_committed_transition() -> None:
    existing = SimpleNamespace(id=17, dedupe_key="same-transition")

    class Savepoint:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _type, _value, _traceback):
            return False

    class Database:
        def __init__(self):
            self.scalar_calls = 0

        async def scalar(self, _statement):
            self.scalar_calls += 1
            return None if self.scalar_calls == 1 else existing

        def begin_nested(self):
            return Savepoint()

        def add(self, _event):
            return None

        async def flush(self):
            raise IntegrityError("insert workflow event", {}, RuntimeError("duplicate"))

    result = asyncio.run(
        append_workflow_event(
            Database(),
            domain="agriculture_analysis",
            stream_id="run-1",
            subject_id="run-1",
            event_type="stage.completed",
            org_id=7,
            user_id=3,
            dedupe_key="same-transition",
        )
    )

    assert result is existing


def test_sensor_fusion_skips_declared_sensors_without_concrete_inputs() -> None:
    class Rows:
        @staticmethod
        def all():
            return []

    class Database:
        async def scalars(self, _statement):
            return Rows()

    result = asyncio.run(
        fuse_sensor_results(
            Database(),
            run=SimpleNamespace(analysis_profile={}),
            flight=SimpleNamespace(
                id="flight-1",
                profile_snapshot={"sensor_inventory": ["rgb", "multispectral"]},
            ),
        )
    )

    assert result.status == "skipped"
    assert result.output["availability"] == "not_available"
    assert result.output["reason"] == "no_sensor_telemetry_or_fusion_inputs"
