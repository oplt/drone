from __future__ import annotations

from pathlib import Path

from backend.core.pagination import CursorPage, OffsetPage, PageMeta


def test_shared_pagination_contracts_are_typed() -> None:
    page = OffsetPage[str](
        items=["a"],
        page=PageMeta(limit=1, offset=0, total=2, next_offset=1),
    )
    cursor = CursorPage[str](items=["a"], next_cursor="next")

    assert page.page.next_offset == 1
    assert cursor.next_cursor == "next"


def test_application_modules_do_not_import_worker_task_modules() -> None:
    root = Path(__file__).parents[1] / "modules"
    offenders: list[str] = []
    for source in root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        if "from backend.entrypoints.workers." in text and "celery_app" not in text:
            offenders.append(str(source))

    assert offenders == []


def test_phase2_migration_is_latest_revision() -> None:
    migration = next(
        Path(__file__).parents[1].glob(
            "infrastructure/persistence/alembic/versions/r4m0i8f3d719_*.py"
        )
    )
    text = migration.read_text(encoding="utf-8")
    assert 'revision: str = "r4m0i8f3d719"' in text
    assert '"irrigation_processing_jobs"' in text


def test_irrigation_image_work_stays_in_worker_boundary() -> None:
    root = Path(__file__).parents[1]
    api_text = (root / "modules/irrigation/api.py").read_text(encoding="utf-8")
    monitor_text = (root / "modules/irrigation/monitor.py").read_text(encoding="utf-8")
    service_text = (root / "modules/irrigation/service/processing.py").read_text(
        encoding="utf-8"
    )
    worker_text = (root / "entrypoints/workers/irrigation_tasks.py").read_text(encoding="utf-8")

    assert "process_mission" not in api_text
    assert "process_mission" not in monitor_text
    assert "import cv2" not in service_text
    assert "process_mission" in worker_text


def test_async_mission_paths_use_vehicle_port_boundary() -> None:
    root = Path(__file__).parents[1]
    paths = [
        root / "modules/missions/planning/photogrammetry.py",
        root / "modules/missions/planning/waypoint.py",
        root / "modules/missions/planning/grid.py",
        root / "modules/patrol/planning.py",
        root / "modules/warehouse/planning/scan.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "asyncio.to_thread(orch.drone" not in text
        assert "async_drone" in text
