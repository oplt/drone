"""Warehouse mapping stack lifecycle — background task tracking."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import deps

logger = logging.getLogger(__name__)


def _track_background_task(task: asyncio.Task[Any]) -> asyncio.Task[Any]:
    background_tasks = deps.resolve("_background_tasks")
    background_tasks.add(task)

    def _cleanup(done: asyncio.Task[Any]) -> None:
        background_tasks.discard(done)
        if done.cancelled():
            return
        try:
            done.exception()
        except Exception:
            logger.exception("background mapping-stack task failed")

    task.add_done_callback(_cleanup)
    return task


__all__ = ["_track_background_task"]
