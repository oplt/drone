from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.infrastructure.warehouse.mapping_stack_process import (
    WarehouseMappingStackProcessManager,
    reset_warehouse_mapping_stack_manager_for_tests,
)

_POPEN = "backend.infrastructure.warehouse.mapping_stack_process.subprocess.Popen"


@pytest.fixture(autouse=True)
def _reset_manager() -> None:
    reset_warehouse_mapping_stack_manager_for_tests()
    yield
    reset_warehouse_mapping_stack_manager_for_tests()


@pytest.fixture
def manager(tmp_path: Path) -> WarehouseMappingStackProcessManager:
    return WarehouseMappingStackProcessManager(log_dir=tmp_path / "logs")


def test_start_when_stopped(manager: WarehouseMappingStackProcessManager) -> None:
    process = MagicMock()
    process.pid = 4242
    process.poll.return_value = None

    with patch(_POPEN, return_value=process):
        status = manager.start()

    assert status.running is True
    assert status.pid == 4242
    assert status.started_at is not None


def test_start_when_already_running_does_not_duplicate(
    manager: WarehouseMappingStackProcessManager,
) -> None:
    process = MagicMock()
    process.pid = 4242
    process.poll.return_value = None

    with patch(_POPEN, return_value=process) as popen:
        manager.start()
        status = manager.start()

    assert popen.call_count == 1
    assert status.running is True
    assert status.pid == 4242


def test_stop_when_running(manager: WarehouseMappingStackProcessManager) -> None:
    process = MagicMock()
    process.pid = 5150
    process.poll.side_effect = [None, None, None, 0]
    process.returncode = 0

    with patch(_POPEN, return_value=process):
        manager.start()
        status = manager.stop()

    assert status.running is False
    assert status.pid is None


def test_stop_when_not_running_is_safe(manager: WarehouseMappingStackProcessManager) -> None:
    status = manager.stop()
    assert status.running is False
    assert status.pid is None


def test_status_reflects_exit_code(manager: WarehouseMappingStackProcessManager) -> None:
    process = MagicMock()
    process.pid = 9001
    process.poll.side_effect = [None, 7]
    process.returncode = 7

    with patch(_POPEN, return_value=process):
        manager.start()
        status = manager.status()

    assert status.running is False
    assert status.last_exit_code == 7


def test_start_failure_sets_last_error(manager: WarehouseMappingStackProcessManager) -> None:
    with patch(
        "backend.infrastructure.warehouse.mapping_stack_process.subprocess.Popen",
        side_effect=OSError("launch failed"),
    ):
        status = manager.start()

    assert status.running is False
    assert status.last_error == "launch failed"


def test_stop_sends_signals_to_process_group(manager: WarehouseMappingStackProcessManager) -> None:
    process = MagicMock()
    process.pid = 7777
    process.poll.side_effect = [None, None, None, None, 0]
    process.returncode = 0

    with (
        patch(_POPEN, return_value=process),
        patch("backend.infrastructure.warehouse.mapping_stack_process.os.killpg") as killpg,
    ):
        manager.start()
        manager.stop()

    assert killpg.call_args_list[0].args == (7777, signal.SIGINT)


def test_cleanup_on_shutdown(manager: WarehouseMappingStackProcessManager) -> None:
    process = MagicMock()
    process.pid = 3333
    process.poll.side_effect = [None, 0]
    process.returncode = 0

    with patch(_POPEN, return_value=process):
        manager.start()
        manager.shutdown()

    status = manager.status()
    assert status.running is False
