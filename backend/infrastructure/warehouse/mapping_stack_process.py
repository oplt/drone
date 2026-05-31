from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = Path("backend/storage/warehouse_ros/logs")
_TERMINATE_TIMEOUT_S = 12.0
_POLL_INTERVAL_S = 0.25

_LAUNCH_SHELL = (
    "if [ -n \"${VIRTUAL_ENV:-}\" ]; then "
    "PATH=\"${PATH//$VIRTUAL_ENV\\/bin:/}\"; "
    "PATH=\"${PATH//:$VIRTUAL_ENV\\/bin/}\"; "
    "PATH=\"${PATH//$VIRTUAL_ENV\\/bin/}\"; "
    "unset VIRTUAL_ENV; "
    "fi; "
    "unset PYTHONPATH PYTHONHOME; "
    "export PYTHONNOUSERSITE=0; "
    "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
    "source \"${ROS_WS_SETUP:-warehouse_ros2_ws/install/setup.bash}\" && "
    "exec ros2 launch warehouse_mapping_bridge isaac_warehouse_mapping.launch.py"
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class MappingStackStatus:
    running: bool
    pid: int | None = None
    started_at: str | None = None
    last_exit_code: int | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "running": self.running,
            "pid": self.pid,
            "started_at": self.started_at,
            "last_exit_code": self.last_exit_code,
            "last_error": self.last_error,
        }


class WarehouseMappingStackProcessManager:
    """Manage the warehouse ROS mapping launch graph as a subprocess."""

    def __init__(self, *, log_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: TextIO | None = None
        self._started_at: str | None = None
        self._last_exit_code: int | None = None
        self._last_error: str | None = None
        self._log_dir = (log_dir or _DEFAULT_LOG_DIR).resolve()
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> MappingStackStatus:
        with self._lock:
            self._refresh_process_state_locked()
            return self._status_locked()

    def start(self) -> MappingStackStatus:
        with self._lock:
            self._refresh_process_state_locked()
            if self._process is not None and self._process.poll() is None:
                return self._status_locked()

            log_path = self._log_dir / "warehouse_mapping_stack.log"
            try:
                log_handle = log_path.open("a", encoding="utf-8")
                log_handle.write(f"\n--- mapping stack start {_utc_now_iso()} ---\n")
                log_handle.flush()
                env = self._ros_launch_env()
                process = subprocess.Popen(
                    ["bash", "-lc", _LAUNCH_SHELL],
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as exc:
                self._last_error = str(exc)
                logger.exception("Failed to start warehouse mapping stack")
                return self._status_locked()

            self._process = process
            self._log_handle = log_handle
            self._started_at = _utc_now_iso()
            self._last_exit_code = None
            self._last_error = None
            logger.info(
                "Warehouse mapping stack started pid=%s log=%s",
                process.pid,
                log_path,
                extra={"pid": process.pid, "log_path": str(log_path)},
            )
            return self._status_locked()

    def stop(self) -> MappingStackStatus:
        with self._lock:
            self._refresh_process_state_locked()
            if self._process is None:
                return self._status_locked()

            process = self._process
            self._terminate_process_group(process)
            self._process = None
            self._close_log_handle()
            self._started_at = None
            return self._status_locked()

    def shutdown(self) -> None:
        self.stop()

    def _status_locked(self) -> MappingStackStatus:
        running = self._process is not None and self._process.poll() is None
        return MappingStackStatus(
            running=running,
            pid=self._process.pid if running and self._process is not None else None,
            started_at=self._started_at if running else None,
            last_exit_code=self._last_exit_code,
            last_error=self._last_error,
        )

    def _refresh_process_state_locked(self) -> None:
        if self._process is None:
            return
        exit_code = self._process.poll()
        if exit_code is None:
            return
        self._last_exit_code = int(exit_code)
        if exit_code != 0 and not self._last_error:
            self._last_error = f"warehouse mapping stack exited with code {exit_code}"
        logger.info(
            "Warehouse mapping stack exited code=%s",
            exit_code,
            extra={"exit_code": exit_code},
        )
        self._process = None
        self._started_at = None
        self._close_log_handle()

    def _terminate_process_group(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            self._last_exit_code = int(process.returncode or 0)
            return
        pid = process.pid
        logger.info("Stopping warehouse mapping stack pid=%s", pid, extra={"pid": pid})
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                self._last_exit_code = int(process.poll() or 0)
                return
            deadline = time.monotonic() + _TERMINATE_TIMEOUT_S
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    self._last_exit_code = int(process.returncode or 0)
                    return
                time.sleep(_POLL_INTERVAL_S)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            logger.warning("Warehouse mapping stack did not exit after SIGKILL pid=%s", pid)
        self._last_exit_code = int(process.returncode or 0)

    def _close_log_handle(self) -> None:
        if self._log_handle is None:
            return
        try:
            self._log_handle.flush()
            self._log_handle.close()
        except OSError:
            pass
        self._log_handle = None

    @staticmethod
    def _ros_launch_env() -> dict[str, str]:
        env = os.environ.copy()
        for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
            env.pop(key, None)
        path = env.get("PATH", "")
        venv_bin = os.path.join(os.getcwd(), ".venv", "bin")
        if venv_bin in path:
            parts = [part for part in path.split(":") if part and part != venv_bin]
            env["PATH"] = ":".join(parts)
        env.setdefault("ROS_DISTRO", "jazzy")
        env.setdefault("ROS_DOMAIN_ID", "42")
        env.setdefault("ROS_WS_SETUP", "warehouse_ros2_ws/install/setup.bash")
        env.setdefault("WAREHOUSE_GAZEBO_SIM", "1")
        env.setdefault("WAREHOUSE_TOPIC_PROFILE", "gazebo")
        env.setdefault("WAREHOUSE_ROS_PROFILE", "gazebo")
        env.setdefault("PYTHONNOUSERSITE", "0")
        return env


_manager: WarehouseMappingStackProcessManager | None = None
_manager_lock = threading.Lock()


def get_warehouse_mapping_stack_manager() -> WarehouseMappingStackProcessManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = WarehouseMappingStackProcessManager()
        return _manager


def reset_warehouse_mapping_stack_manager_for_tests() -> None:
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.shutdown()
        _manager = None
