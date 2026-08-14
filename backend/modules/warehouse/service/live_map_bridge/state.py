"""Warehouse live-map bridge — module runtime state."""

from __future__ import annotations

import asyncio

_bridge_task: asyncio.Task[None] | None = None
_bridge_flight_id: str | None = None
_bridge_stop: asyncio.Event | None = None
_bridge_lock = asyncio.Lock()

__all__ = [
    "_bridge_flight_id",
    "_bridge_lock",
    "_bridge_stop",
    "_bridge_task",
]
