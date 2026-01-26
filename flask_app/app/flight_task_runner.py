import subprocess
import sys
import os
import logging
import time
import signal
from typing import Optional, Tuple

# Global flight task process handle
_flight_task_process: Optional[subprocess.Popen] = None


def start_flight_task_async(
    start_lat: float,
    start_lon: float,
    start_alt: float,
    dest_lat: float,
    dest_lon: float,
    dest_alt: float,
    user_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    Start flight task in a separate process, passing coordinates as CLI args.

    Returns:
        (ok, message)
    """
    global _flight_task_process

    # Prevent multiple concurrent runs
    if _flight_task_process and _flight_task_process.poll() is None:
        logging.warning("Flight task is already running")
        return False, "Flight task is already running"

    # Basic validation (defensive)
    try:
        start_lat = float(start_lat)
        start_lon = float(start_lon)
        dest_lat = float(dest_lat)
        dest_lon = float(dest_lon)
        start_alt = float(start_alt)
        dest_alt = float(dest_alt)
    except (ValueError, TypeError) as e:
        return False, f"Invalid coordinate format: {e}"

    if not (-90.0 <= start_lat <= 90.0 and -180.0 <= start_lon <= 180.0):
        return False, "Invalid start coordinates"
    if not (-90.0 <= dest_lat <= 90.0 and -180.0 <= dest_lon <= 180.0):
        return False, "Invalid destination coordinates"
    if start_alt < 0 or dest_alt < 0:
        return False, "Altitude must be positive"

    try:
        # Determine project root and main.py path
        # (kept consistent with your existing runner style)
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        main_py_path = os.path.join(project_root, "main.py")

        if not os.path.exists(main_py_path):
            error_msg = f"main.py not found at {main_py_path}"
            logging.error(error_msg)
            return False, error_msg

        # Build CLI command (coordinates passed explicitly)
        cmd = [
            sys.executable,
            "-u",
            main_py_path,
            "--start-lat",
            str(start_lat),
            "--start-lon",
            str(start_lon),
            "--start-alt",
            str(start_alt),
            "--dest-lat",
            str(dest_lat),
            "--dest-lon",
            str(dest_lon),
            "--dest-alt",
            str(dest_alt),
        ]
        if user_id is not None:
            cmd += ["--user-id", str(user_id)]

        # All logs go to drone.log in project root
        drone_log_file = os.path.join(project_root, "drone.log")

        # Write an initial header to drone.log
        with open(drone_log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 80}\n")
            f.write(f"Starting flight task at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(
                f"Coordinates: Start ({start_lat}, {start_lon}, alt={start_alt}) "
                f"-> End ({dest_lat}, {dest_lon}, alt={dest_alt})\n"
            )
            f.write(f"User ID: {user_id}\n")
            f.write(f"Working directory: {project_root}\n")
            f.write(f"{'=' * 80}\n\n")

        env = os.environ.copy()  # Keep general config env vars, but NOT coordinates

        try:
            # Redirect both stdout and stderr to drone.log
            with open(drone_log_file, "a", encoding="utf-8") as log_f:
                _flight_task_process = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout
                    cwd=project_root,
                    env=env,
                    start_new_session=True,  # creates a new process group/session
                )

            # Give it a moment to fail fast (missing args, import errors, etc.)
            time.sleep(1.0)

            if _flight_task_process.poll() is not None:
                # Process exited immediately - read from drone.log
                error_output = ""
                try:
                    with open(drone_log_file, "r", encoding="utf-8") as f:
                        # Read last 2000 characters for recent errors
                        f.seek(0, 2)  # Seek to end
                        file_size = f.tell()
                        f.seek(max(0, file_size - 2000), 0)  # Read last 2000 chars
                        error_output = f.read()
                except Exception as e:
                    error_output = f"Could not read error output: {e}"

                exit_code = _flight_task_process.returncode
                error_msg = (
                    f"Process exited immediately with code {exit_code}. "
                    f"Error: {error_output[:2000] if error_output else 'No error output'}"
                )
                logging.error(error_msg)
                return False, error_msg

            logging.info(f"Flight task started with PID: {_flight_task_process.pid}")
            logging.info(
                f"Coordinates: Start ({start_lat}, {start_lon}, alt={start_alt}) "
                f"-> End ({dest_lat}, {dest_lon}, alt={dest_alt})"
            )
            logging.info(f"User ID: {user_id}")
            logging.info(f"All logs written to: {drone_log_file}")
            return (
                True,
                f"Flight task started (PID: {_flight_task_process.pid}). "
                f"All logs written to drone.log",
            )

        except Exception as e:
            error_msg = f"Failed to start subprocess: {str(e)}"
            logging.error(error_msg, exc_info=True)
            return False, error_msg

    except Exception as e:
        logging.error(f"Error starting flight task: {e}", exc_info=True)
        return False, f"Error starting flight task: {str(e)}"


def stop_flight_task() -> Tuple[bool, str]:
    """
    Stop the running flight task.

    Because we started the subprocess with start_new_session=True,
    it runs in its own process group. We terminate the whole group to avoid orphans.
    """
    global _flight_task_process

    if not _flight_task_process or _flight_task_process.poll() is not None:
        return False, "No flight task running"

    try:
        pid = _flight_task_process.pid

        # Send SIGTERM to the process group
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            # Fallback: terminate the process itself
            _flight_task_process.terminate()

        try:
            _flight_task_process.wait(timeout=5)
            return True, "Flight task stopped"
        except subprocess.TimeoutExpired:
            # Force kill process group
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                _flight_task_process.kill()

            _flight_task_process.wait(timeout=5)
            return True, "Flight task force stopped"

    except Exception as e:
        logging.error(f"Error stopping flight task: {e}", exc_info=True)
        return False, f"Error stopping flight task: {str(e)}"


def is_flight_task_running() -> bool:
    """Return True if the flight subprocess exists and is still running."""
    global _flight_task_process
    return _flight_task_process is not None and _flight_task_process.poll() is None
