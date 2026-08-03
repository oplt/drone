"""Dependency inversion ports for agriculture persistence and object storage."""

from typing import Protocol

from backend.modules.agriculture.storage import AgricultureObjectStoragePort


class AgricultureWorkerPort(Protocol):
    async def enqueue_analysis(self, flight_id: str, *, idempotency_key: str) -> str: ...


__all__ = ["AgricultureObjectStoragePort", "AgricultureWorkerPort"]
