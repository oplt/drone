from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path


def start_process(
    command: str | list[str],
    *,
    env: dict[str, str],
    log_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    cmd = shlex.split(command) if isinstance(command, str) else command
    if log_path is None:
        return subprocess.Popen(cmd, env=env, start_new_session=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    try:
        return subprocess.Popen(
            cmd,
            env=env,
            start_new_session=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    finally:
        log_file.close()


def exited_during_grace(process: subprocess.Popen[bytes], *, grace_s: float) -> bool:
    if grace_s > 0:
        time.sleep(min(grace_s, 5.0))
    return process.poll() is not None


def terminate_process(process: subprocess.Popen[bytes], *, timeout_s: float = 8.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
