from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass
class Client:
    ws: WebSocket
    q: asyncio.Queue
    task: asyncio.Task
    connected_time: float
    client_host: str | None = None
    client_port: int | None = None
    user_agent: str | None = None
    user_id: int | None = None
    org_id: int | None = None
    mission_runtime_id: str | None = None
    wire_protocol: str = "legacy"
