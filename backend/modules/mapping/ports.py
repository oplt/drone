from __future__ import annotations

from typing import Any, Protocol


class MappingProcessorPort(Protocol):
    async def create_task(
        self, *, job_id: int, options: dict[str, Any], image_paths: list[str]
    ) -> str: ...

    async def get_task_status(self, task_id: str) -> dict[str, Any]: ...

    async def download_outputs(self, task_id: str) -> dict[str, str]: ...


class MappingStoragePort(Protocol):
    async def upload_file(self, src_path: str) -> str: ...

    async def upload_directory(self, src_dir: str) -> str: ...


class MappingImageIngestPort(Protocol):
    def collect_images_for_job(
        self, *, job_id: int, field_id: int, params: dict[str, Any]
    ) -> list[str]: ...
