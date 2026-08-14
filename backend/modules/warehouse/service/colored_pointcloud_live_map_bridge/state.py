"""Colored point-cloud live-map bridge — runtime state."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from backend.modules.warehouse.service.map_source_config import LiveMapSourceConfig


@dataclass
class _SourceRuntime:
    config: LiveMapSourceConfig
    sequence: int = 0
    last_publish_monotonic: float = 0.0
    queued_msg: Any | None = None
    processing: bool = False
    dropped_frames: int = 0
    last_backpressure_log_monotonic: float = 0.0
    last_content_digest: str | None = None
    duplicate_chunks_skipped: int = 0
    messages_received: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass
class _ColoredBridgeRuntime:
    node: Any
    executor: Any
    thread: threading.Thread
    sources: dict[str, _SourceRuntime]


_runtime: _ColoredBridgeRuntime | None = None
_runtime_lock = asyncio.Lock()

__all__ = [
    "_ColoredBridgeRuntime",
    "_SourceRuntime",
    "_runtime",
    "_runtime_lock",
]
