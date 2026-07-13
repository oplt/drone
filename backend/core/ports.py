"""Stable ports shared by HTTP adapters and worker implementations."""

from __future__ import annotations

from typing import Any, Protocol


class QueuePort(Protocol):
    def enqueue(self, task_name: str, *, queue: str | None = None, **kwargs: Any) -> str: ...


class StoragePort(Protocol):
    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str: ...

    async def delete(self, key: str) -> None: ...


class AIProviderPort(Protocol):
    async def complete(self, *, prompt: str, model: str | None = None, **kwargs: Any) -> Any: ...
