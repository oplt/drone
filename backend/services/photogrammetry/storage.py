from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from uuid import uuid4


class StorageService:
    """
    Local storage shim.

    In production, replace with S3/MinIO adapter while keeping the same method
    signatures (`upload_file`, `upload_directory`).
    """

    def __init__(self) -> None:
        self.storage_dir = Path(
            os.getenv("PHOTOGRAMMETRY_STORAGE_DIR", "backend/storage/mapping")
        ).resolve()
        self.base_url = os.getenv("PHOTOGRAMMETRY_STORAGE_BASE_URL", "/mapping-assets").rstrip(
            "/"
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def upload_file(self, src_path: str) -> str:
        src = Path(src_path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"File not found for upload: {src}")

        suffix = src.suffix.lower()
        target_name = f"{src.stem}-{uuid4().hex[:10]}{suffix}"
        dst = self.storage_dir / target_name
        await asyncio.to_thread(shutil.copy2, src, dst)
        return f"{self.base_url}/{target_name}"

    async def upload_directory(self, src_dir: str) -> str:
        src = Path(src_dir).resolve()
        if not src.exists() or not src.is_dir():
            raise FileNotFoundError(f"Directory not found for upload: {src}")

        target_name = f"{src.name}-{uuid4().hex[:10]}"
        dst = self.storage_dir / target_name
        await asyncio.to_thread(shutil.copytree, src, dst)
        return f"{self.base_url}/{target_name}"
