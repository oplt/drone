from __future__ import annotations

import contextlib
import logging
import os
import signal
import socket
import subprocess
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse
import json
import shlex
import textwrap

from backend.modules.warehouse.service.bridge_flow import (
    flow_env_overrides,
    resolve_warehouse_bridge_flow,
)

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = Path("backend/storage/warehouse_ros/logs")
_TERMINATE_TIMEOUT_S = 8.0
_POLL_INTERVAL_S = 0.2


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BridgeStackStatus:
    running: bool
    pid: int | None = None
    started_at: str | None = None
    last_exit_code: int | None = None
    last_error: str | None = None
    state: str = "stopped"
    run_id: str | None = None
    log_path: str | None = None
    exit_at: str | None = None
    stop_reason: str | None = None
    last_output: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "running": self.running,
            "pid": self.pid,
            "started_at": self.started_at,
            "last_exit_code": self.last_exit_code,
            "last_error": self.last_error,
            "state": self.state,
            "run_id": self.run_id,
            "log_path": self.log_path,
            "exit_at": self.exit_at,
            "stop_reason": self.stop_reason,
            "last_output": self.last_output,
        }


class WarehouseBridgeStackProcessManager:
    """Start the lightweight ROS/Gazebo bridge graph only when preflight needs it."""

    def __init__(self, *, log_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: TextIO | None = None
        self._started_at: str | None = None
        self._last_exit_code: int | None = None
        self._last_error: str | None = None
        self._run_id: str | None = None
        self._log_path: Path | None = None
        self._exit_at: str | None = None
        self._stop_reason: str | None = None
        self._external_started_at: str | None = None
        self._log_dir = (log_dir or _DEFAULT_LOG_DIR).resolve()
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> BridgeStackStatus:
        with self._lock:
            self._refresh_locked()
            if self._process is None and self._external_bridge_alive():
                self._adopt_external_locked()
            return self._status_locked()

    def start(
            self, *, restart: bool = False, stop_reason: str = "health_restart"
    ) -> BridgeStackStatus:
        with self._lock:
            self._refresh_locked()
            external_bridge = self._external_bridge_alive()
            if external_bridge and not restart:
                self._adopt_external_locked()
            if restart and self._process is not None:
                self._stop_reason = stop_reason
                self._terminate_process_group(self._process)
                self._process = None
                self._started_at = None
                self._close_log_handle()
            if restart:
                self._external_started_at = None
            if self._process is not None and self._process.poll() is None:
                return self._status_locked()

            run_id = uuid.uuid4().hex[:12]
            started_at = _utc_now_iso()
            log_path = (
                    self._log_dir / f"warehouse_bridge_stack_{started_at.replace(':', '')}_{run_id}.log"
            )
            repo_root = Path(__file__).resolve().parents[3]
            try:
                log_handle = log_path.open("a", encoding="utf-8")
                log_handle.write(
                    f"\n--- bridge stack start run_id={run_id} started_at={started_at} ---\n"
                )
                log_handle.flush()
                process = subprocess.Popen(
                    ["bash", "-lc", self._build_launch_shell()],
                    env=self._env(),
                    cwd=str(repo_root),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as exc:
                self._last_error = str(exc)
                logger.exception("Failed to start warehouse bridge stack")
                return self._status_locked()

            self._process = process
            self._log_handle = log_handle
            self._started_at = started_at
            self._last_exit_code = None
            self._last_error = None
            self._run_id = run_id
            self._log_path = log_path
            self._exit_at = None
            self._stop_reason = None
            self._external_started_at = None
            logger.info(
                "Warehouse bridge stack started run_id=%s pid=%s started_at=%s log=%s",
                run_id,
                process.pid,
                started_at,
                log_path,
                extra={
                    "run_id": run_id,
                    "pid": process.pid,
                    "started_at": started_at,
                    "log_path": str(log_path),
                },
            )
            return self._status_locked()

    def stop(self, *, reason: str = "manual_stop") -> BridgeStackStatus:
        with self._lock:
            self._refresh_locked()
            if self._process is None:
                return self._status_locked()
            self._stop_reason = reason
            self._terminate_process_group(self._process)
            self._process = None
            self._started_at = None
            self._close_log_handle()
            return self._status_locked()

    def shutdown(self) -> None:
        self.stop()

    @classmethod
    def _rosbridge_port(cls) -> int:
        raw = os.getenv("ROSBRIDGE_PORT", "9090").strip()
        try:
            return int(raw)
        except ValueError:
            return 9090

    @classmethod
    def _bridge_port(cls) -> int:
        url = os.getenv("WAREHOUSE_ROS_BRIDGE_URL", "http://127.0.0.1:8088").strip()
        if "://" not in url:
            url = f"http://{url}"
        parsed = urlparse(url)
        return parsed.port or 8088

    @classmethod
    def _local_port_in_use(cls, port: int, host: str = "127.0.0.1") -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.25)
                return sock.connect_ex((host, port)) == 0
        except OSError:
            return False

    @classmethod
    def _build_launch_shell(cls) -> str:
        flow = resolve_warehouse_bridge_flow()
        if flow.name != "gazebo":
            return textwrap.dedent(f"""
            set -Eeuo pipefail
            source /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash
            if [ -f "${{ROS_WS_SETUP:-warehouse_ros2_ws/install/setup.bash}}" ]; then
              source "${{ROS_WS_SETUP:-warehouse_ros2_ws/install/setup.bash}}"
            else
              echo "[warehouse_bridge_stack] WARNING: ROS workspace setup not found: ${{ROS_WS_SETUP:-warehouse_ros2_ws/install/setup.bash}}"
              export PYTHONPATH="$(pwd)/warehouse_ros2_ws/src/warehouse_mapping_bridge:${{PYTHONPATH:-}}"
            fi
            export WAREHOUSE_BRIDGE_FLOW={flow.name}
            export WAREHOUSE_TOPIC_PROFILE={flow.topic_profile}
            export WAREHOUSE_ROS_PROFILE={flow.ros_profile}
            export WAREHOUSE_GAZEBO_SIM=0
            exec ros2 launch warehouse_mapping_bridge {flow.launch_file} \\
              use_sim_time:={'true' if flow.use_sim_time else 'false'} \\
              rosbridge_port:=${{ROSBRIDGE_PORT:-9090}}
            """).strip()

        bridge_up = cls._external_bridge_alive()
        rosbridge_up = cls._local_port_in_use(cls._rosbridge_port())

        clean_stale_raw = (
            "0" if bridge_up else os.getenv("WAREHOUSE_PREFLIGHT_CLEAN_STALE_BRIDGE", "1")
        )
        clean_stale = (
            "1"
            if str(clean_stale_raw).strip().lower() in {"1", "true", "yes", "on"}
            else "0"
        )

        bridge_port = int(cls._bridge_port())
        rosbridge_port = int(cls._rosbridge_port())

        return textwrap.dedent(f"""
    set -Eeuo pipefail
    
    children=()
    
    shutdown_children() {{
      local sig="${{1:-TERM}}"
      for pid in "${{children[@]:-}}"; do
        if [ -n "${{pid:-}}" ] && kill -0 "$pid" 2>/dev/null; then
          kill -s "$sig" "$pid" 2>/dev/null || true
        fi
      done
    }}
    
    trap 'rc=$?; echo "[warehouse_bridge_stack] EXIT rc=${{rc}} jobs:"; jobs -l || true; shutdown_children TERM; exit $rc' EXIT
    trap 'echo "[warehouse_bridge_stack] SIGTERM received"; jobs -l || true; shutdown_children TERM; exit 143' TERM
    trap 'echo "[warehouse_bridge_stack] SIGINT received"; jobs -l || true; shutdown_children INT; exit 130' INT
    
    export WAREHOUSE_PREFLIGHT_CLEAN_STALE_BRIDGE={clean_stale}
    export WAREHOUSE_SKIP_BRIDGE_LAUNCH={'1' if bridge_up else '0'}
    export WAREHOUSE_SKIP_ROSBRIDGE_LAUNCH={'1' if rosbridge_up else '0'}
    export WAREHOUSE_ROS_BRIDGE_PORT={bridge_port}
    export ROSBRIDGE_PORT="${{ROSBRIDGE_PORT:-{rosbridge_port}}}"
    
    echo "[warehouse_bridge_stack] launch shell pid=$$ pwd=$(pwd)"
    echo "[warehouse_bridge_stack] ROS_DISTRO=${{ROS_DISTRO:-unset}} ROS_DOMAIN_ID=${{ROS_DOMAIN_ID:-unset}}"
    echo "[warehouse_bridge_stack] ROS_WS_SETUP=${{ROS_WS_SETUP:-unset}}"
    echo "[warehouse_bridge_stack] skip_bridge=${{WAREHOUSE_SKIP_BRIDGE_LAUNCH}} skip_rosbridge=${{WAREHOUSE_SKIP_ROSBRIDGE_LAUNCH}} clean_stale=${{WAREHOUSE_PREFLIGHT_CLEAN_STALE_BRIDGE}}"
    
    port_in_use() {{
      python3 - "$1" <<'PY'
    import socket
    import sys
    
    port = int(sys.argv[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
    PY
    }}
    
    source_ros() {{
      if [ ! -f "/opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash" ]; then
        echo "[warehouse_bridge_stack] ERROR: /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash not found"
        exit 97
      fi
    
      set +u
      source "/opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash"
    
      if [ -f "${{ROS_WS_SETUP}}" ]; then
        source "${{ROS_WS_SETUP}}"
      else
        echo "[warehouse_bridge_stack] WARNING: ROS workspace setup not found: ${{ROS_WS_SETUP}}"
        export PYTHONPATH="$(pwd)/warehouse_ros2_ws/src/warehouse_mapping_bridge:${{PYTHONPATH:-}}"
      fi
      set -u
    }}

    run_warehouse_node() {{
      local executable="$1"
      local module="$2"
      if ros2 pkg prefix warehouse_mapping_bridge >/dev/null 2>&1; then
        bash scripts/procfile.sh ros2 run warehouse_mapping_bridge "$executable"
      else
        echo "[warehouse_bridge_stack] package not installed; running source module $module"
        WAREHOUSE_BRIDGE_PYTHON="${{WAREHOUSE_BRIDGE_PYTHON:-$(pwd)/.venv/bin/python}}"
        if [ ! -x "$WAREHOUSE_BRIDGE_PYTHON" ]; then
          WAREHOUSE_BRIDGE_PYTHON="$(command -v python3)"
        fi
        PYTHONPATH="$(pwd)/warehouse_ros2_ws/src/warehouse_mapping_bridge:${{PYTHONPATH:-}}" \\
          "$WAREHOUSE_BRIDGE_PYTHON" -m "$module"
      fi
    }}
    
    safe_kill_pattern() {{
      local pattern="$1"
      local sig="${{2:-TERM}}"
      local self="$$"
      local self_pgid
      self_pgid="$(ps -o pgid= -p "$self" 2>/dev/null | tr -d ' ' || true)"
    
      while read -r pid cmd; do
        [ -z "${{pid:-}}" ] && continue
        [ "$pid" = "$self" ] && continue
    
        local pgid
        pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    
        # Never kill the current launcher process group.
        if [ -n "$self_pgid" ] && [ "$pgid" = "$self_pgid" ]; then
          continue
        fi

        # The generated supervisor script contains every child command in its
        # own "bash -lc ..." argv. A plain pgrep match against the full command
        # line would therefore treat launcher shells as component processes.
        case "$cmd" in
          *"[warehouse_bridge_stack]"*|*"safe_kill_pattern"*|*"start_if_missing"*)
            continue
            ;;
        esac
    
        echo "[warehouse_bridge_stack] killing stale pid=$pid pattern=$pattern cmd=$cmd"
        kill -s "$sig" "$pid" 2>/dev/null || true
      done < <(pgrep -af "$pattern" 2>/dev/null || true)
    }}
    
    start_if_missing() {{
      local pattern="$1"
      shift
    
      while read -r pid cmd; do
        [ -z "${{pid:-}}" ] && continue
        [ "$pid" = "$$" ] && continue
        case "$cmd" in
          *"[warehouse_bridge_stack]"*|*"safe_kill_pattern"*|*"start_if_missing"*)
            continue
            ;;
        esac
        echo "[warehouse_bridge_stack] already running: $pattern pid=$pid cmd=$cmd"
        return 0
      done < <(pgrep -af "$pattern" 2>/dev/null || true)
    
      echo "[warehouse_bridge_stack] starting: $*"
      "$@" &
      children+=("$!")
    }}
    
    source_ros
    
    if [ "${{WAREHOUSE_PREFLIGHT_CLEAN_STALE_BRIDGE}}" = "1" ]; then
      echo "[warehouse_bridge_stack] cleaning stale bridge processes"
      safe_kill_pattern 'warehouse_bridge_service'
      safe_kill_pattern 'warehouse_sim_tf_broadcaster'
      safe_kill_pattern 'warehouse_odometry_export'
    
      if [ "${{WAREHOUSE_SKIP_ROSBRIDGE_LAUNCH}}" != "1" ]; then
        safe_kill_pattern 'rosbridge_websocket'
        safe_kill_pattern 'rosapi_node'
      fi
    
      safe_kill_pattern 'ros_gz_bridge'
      sleep 0.5
    fi

    if [ "${{WAREHOUSE_SKIP_BRIDGE_LAUNCH}}" != "1" ] && port_in_use "${{WAREHOUSE_ROS_BRIDGE_PORT}}"; then
      echo "[warehouse_bridge_stack] ERROR: port ${{WAREHOUSE_ROS_BRIDGE_PORT}} is occupied, but /health is not a valid warehouse bridge"
      command -v ss >/dev/null 2>&1 && ss -ltnp | grep ":${{WAREHOUSE_ROS_BRIDGE_PORT}}" || true
      exit 98
    fi
    
    start_if_missing 'start_gazebo_sensor_bridge.sh' \\
      bash -lc 'exec bash "$(pwd)/scripts/start_gazebo_sensor_bridge.sh"'

    start_if_missing 'warehouse_topic_adapter' \\
      run_warehouse_node warehouse_topic_adapter warehouse_mapping_bridge.topic_adapter_node
    
    start_if_missing 'warehouse_sim_tf_broadcaster' \\
      run_warehouse_node warehouse_sim_tf_broadcaster warehouse_mapping_bridge.sim_tf_broadcaster_node
    
    start_if_missing 'warehouse_odometry_export' \\
      run_warehouse_node warehouse_odometry_export warehouse_mapping_bridge.odometry_export_node
    
    if [ "${{WAREHOUSE_SKIP_BRIDGE_LAUNCH}}" != "1" ]; then
      echo "[warehouse_bridge_stack] starting warehouse_bridge.sh"
      bash ./scripts/warehouse_bridge.sh &
      children+=("$!")
    else
      echo "[warehouse_bridge_stack] warehouse bridge health endpoint is alive — skipping warehouse_bridge.sh"
    fi
    
    if [ "${{WAREHOUSE_SKIP_ROSBRIDGE_LAUNCH}}" != "1" ]; then
      echo "[warehouse_bridge_stack] starting rosbridge websocket on port ${{ROSBRIDGE_PORT}}"
      bash scripts/procfile.sh ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:=${{ROSBRIDGE_PORT}} &
      children+=("$!")
    else
      echo "[warehouse_bridge_stack] rosbridge port already in use — skipping launch"
    fi
    
    if [ "${{#children[@]}}" -eq 0 ]; then
      echo "[warehouse_bridge_stack] no managed children; keeping supervisor process alive"
      while true; do sleep 3600; done
    fi
    
    wait -n || exit "$?"
    """).strip()

    @classmethod
    def _env(cls) -> dict[str, str]:
        env = os.environ.copy()
        repo_root = Path(__file__).resolve().parents[3]

        for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
            env.pop(key, None)

        venv_bins = {
            str(repo_root / ".venv/bin"),
            str(repo_root / "backend/.venv/bin"),
        }
        path = env.get("PATH", "")
        env["PATH"] = ":".join(part for part in path.split(":") if part and part not in venv_bins)

        env.setdefault("ROS_DISTRO", "jazzy")
        env.setdefault("ROS_DOMAIN_ID", "42")
        env.setdefault("ROS_WS_SETUP", str(repo_root / "warehouse_ros2_ws/install/setup.bash"))

        env.update(flow_env_overrides())
        if env["WAREHOUSE_BRIDGE_FLOW"] == "gazebo":
            env.setdefault("WAREHOUSE_BASE_LINK_FRAME", "iris_with_standoffs/base_link")

        # Important for real Gazebo readiness, not only HTTP-process readiness.
        if env["WAREHOUSE_BRIDGE_FLOW"] == "gazebo":
            env.setdefault("WAREHOUSE_GAZEBO_REQUIRE_PUBLISHING", "0")
            env.setdefault("WAREHOUSE_GAZEBO_SENSOR_WAIT_S", "60")
            env.setdefault("WAREHOUSE_BRIDGE_WAIT_FOR_TOPICS", "0")
            env.setdefault("WAREHOUSE_GAZEBO_PROBE_ON_HEALTH", "1")
        env.setdefault("WAREHOUSE_TF_PROBE_ON_HEALTH", "1")
        env.setdefault("WAREHOUSE_BRIDGE_PYTHON", str(repo_root / ".venv/bin/python"))
        env.setdefault("PYTHONNOUSERSITE", "0")

        bridge_up = cls._external_bridge_alive()
        rosbridge_up = cls._local_port_in_use(cls._rosbridge_port())

        env["WAREHOUSE_SKIP_BRIDGE_LAUNCH"] = "1" if bridge_up else "0"
        env["WAREHOUSE_SKIP_ROSBRIDGE_LAUNCH"] = "1" if rosbridge_up else "0"
        env.setdefault("WAREHOUSE_PREFLIGHT_CLEAN_STALE_BRIDGE", "0" if bridge_up else "1")

        return env

    @staticmethod
    def _external_bridge_health_timeout_s() -> float:
        raw = os.getenv("WAREHOUSE_BRIDGE_HEALTH_PROBE_TIMEOUT_S", "2.0").strip()
        try:
            return max(0.35, float(raw))
        except ValueError:
            return 2.0

    @staticmethod
    def _external_bridge_alive() -> bool:
        raw_url = os.getenv("WAREHOUSE_ROS_BRIDGE_URL", "http://127.0.0.1:8088").strip()
        if not raw_url:
            raw_url = "http://127.0.0.1:8088"
        if "://" not in raw_url:
            raw_url = f"http://{raw_url}"
        url = raw_url.rstrip("/")

        try:
            request = urllib.request.Request(
                f"{url}/health",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(
                request,
                timeout=WarehouseBridgeStackProcessManager._external_bridge_health_timeout_s(),
            ) as response:
                status = int(response.status)
                body = response.read(8192).decode("utf-8", errors="replace")
        except (OSError, urllib.error.URLError, TimeoutError):
            return False

        if not (200 <= status < 300):
            return False

        try:
            payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            return False

        if not isinstance(payload, dict):
            return False

        negative_status = str(payload.get("status", "")).strip().lower()
        if negative_status in {"disabled", "unreachable", "failed", "error"}:
            return False

        # Recognize the actual warehouse bridge, not just any HTTP server on 8088.
        known_bridge_keys = {
            "ready",
            "healthy",
            "status",
            "components",
            "profile",
            "capabilities",
            "websocket_url",
            "capture_root",
        }
        return any(key in payload for key in known_bridge_keys)

    def _status_locked(self) -> BridgeStackStatus:
        running = self._process is not None and self._process.poll() is None
        external_running = not running and self._external_bridge_alive()
        if external_running and self._external_started_at is None:
            self._external_started_at = _utc_now_iso()
        return BridgeStackStatus(
            running=running or external_running,
            pid=self._process.pid if running and self._process is not None else None,
            started_at=self._started_at if running else self._external_started_at,
            last_exit_code=self._last_exit_code,
            last_error=self._last_error,
            state="process_running" if running or external_running else "stopped",
            run_id=self._run_id if running else None,
            log_path=str(self._log_path) if self._log_path else None,
            exit_at=self._exit_at,
            stop_reason=self._stop_reason,
            last_output=self._tail_log_locked(),
        )



    def _refresh_locked(self) -> None:
        if self._process is None:
            return
        exit_code = self._process.poll()
        if exit_code is None:
            return
        self._last_exit_code = int(exit_code)
        self._exit_at = _utc_now_iso()
        if self._stop_reason is None:
            self._stop_reason = "crash" if exit_code != 0 else "process_exit"
        if exit_code != 0 and not self._last_error:
            self._last_error = f"warehouse bridge stack exited with code {exit_code}"
        logger.info(
            "Warehouse bridge stack exited run_id=%s pid=%s exit_at=%s code=%s stop_reason=%s",
            self._run_id,
            self._process.pid,
            self._exit_at,
            exit_code,
            self._stop_reason,
        )
        self._process = None
        self._started_at = None
        self._close_log_handle()

    def _adopt_external_locked(self) -> None:
        if self._external_started_at is None:
            self._external_started_at = _utc_now_iso()
        self._last_error = None

    def _tail_log_locked(self, limit: int = 40) -> list[str]:
        if self._log_path is None or not self._log_path.exists():
            return []
        try:
            return self._log_path.read_text(encoding="utf-8", errors="replace").splitlines()[
                -limit:
            ]
        except OSError:
            return []

    def _terminate_process_group(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            self._last_exit_code = int(process.returncode or 0)
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, sig)
            deadline = time.monotonic() + _TERMINATE_TIMEOUT_S
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    self._last_exit_code = int(process.returncode or 0)
                    return
                time.sleep(_POLL_INTERVAL_S)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=3.0)
        self._last_exit_code = int(process.returncode or 0)

    def _close_log_handle(self) -> None:
        if self._log_handle is None:
            return
        with contextlib.suppress(OSError):
            self._log_handle.flush()
            self._log_handle.close()
        self._log_handle = None


_manager: WarehouseBridgeStackProcessManager | None = None
_manager_lock = threading.Lock()


def get_warehouse_bridge_stack_manager() -> WarehouseBridgeStackProcessManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = WarehouseBridgeStackProcessManager()
        return _manager


def reset_warehouse_bridge_stack_manager_for_tests() -> None:
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.shutdown()
        _manager = None
