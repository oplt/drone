from __future__ import annotations

from typing import Protocol


class DeliverableStoragePort(Protocol):
    async def save(
        self, *, org_id: int | None, deliverable_id: int, filename: str, content: bytes
    ) -> str: ...
