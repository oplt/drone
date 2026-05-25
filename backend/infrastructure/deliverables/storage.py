from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from backend.core.config.runtime import settings
from backend.infrastructure.storage import ObjectStorageClient


class DeliverableStorage:
    async def save(
        self, *, org_id: int | None, deliverable_id: int, filename: str, content: bytes
    ) -> str:
        if settings.storage_backend == "s3":
            prefix = f"orgs/{org_id}" if org_id is not None else "orgs/shared"
            key = f"{prefix}/deliverables/{deliverable_id}/{filename}"
            with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix) as temp_file:
                temp_file.write(content)
                temp_file.flush()
                await ObjectStorageClient().upload_file(Path(temp_file.name), key)
            return key
        directory = Path("backend/storage/deliverables") / str(deliverable_id)
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        path = directory / filename
        await asyncio.to_thread(path.write_bytes, content)
        return str(path)
