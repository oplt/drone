"""Raw point-cloud live-map bridge — runtime state."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class _RawPointCloudRuntime:
    node: Any
    executor: Any
    thread: threading.Thread
    wrapper: Any


_runtime: _RawPointCloudRuntime | None = None
_runtime_lock = asyncio.Lock()

__all__ = ["_RawPointCloudRuntime", "_runtime", "_runtime_lock"]
