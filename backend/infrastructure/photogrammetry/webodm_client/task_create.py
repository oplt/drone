from __future__ import annotations

import json
import logging
import mimetypes
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TaskCreateMixin:
    """Task creation for WebODM and NodeODM backends."""

    async def create_task(
        self,
        *,
        job_id: int,
        options: dict[str, Any] | None = None,
        image_paths: list[str] | None = None,
    ) -> str:
        if self.mock_mode:
            logger.info("WebODM create_task mock mode: job_id=%s", job_id)
            return f"mock-{job_id}"

        resolved_images = self._resolve_image_paths(image_paths)
        backend_kind = await self._get_backend_kind()
        logger.info(
            "Photogrammetry create_task start: job_id=%s images=%s project_id=%s backend=%s",
            job_id,
            len(resolved_images),
            self.project_id,
            backend_kind,
        )
        if len(resolved_images) > self.upload_batch_size:
            raise RuntimeError(
                "WebODM upload received "
                f"{len(resolved_images)} images, exceeding "
                f"WEBODM_UPLOAD_BATCH_SIZE={self.upload_batch_size}. "
                "This client uploads images in one multipart request "
                "(one open file descriptor per image); increase "
                "WEBODM_UPLOAD_BATCH_SIZE only if your OS ulimit supports it, "
                "or add chunked upload support."
            )

        if backend_kind == "nodeodm":
            return await self._create_task_nodeodm(
                job_id=job_id,
                options=options,
                resolved_images=resolved_images,
            )
        return await self._create_task_webodm(
            job_id=job_id,
            options=options,
            resolved_images=resolved_images,
        )

    async def _create_task_webodm(
        self,
        *,
        job_id: int,
        options: dict[str, Any] | None,
        resolved_images: list[Path],
    ) -> str:

        url = f"{self.base_url}/api/projects/{self.project_id}/tasks/"
        data = {
            "name": f"mapping-job-{job_id}",
            "options": json.dumps(options or {}),
        }

        with ExitStack() as stack:
            files = []
            for image in resolved_images:
                fh = stack.enter_context(image.open("rb"))
                mime_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
                files.append(("images", (image.name, fh, mime_type)))

            async with httpx.AsyncClient(timeout=self.http_timeout_s) as client:
                resp = await client.post(
                    url,
                    headers=self._headers(),
                    data=data,
                    files=files,
                )
                resp.raise_for_status()
                payload = resp.json()

        task_id = payload.get("id")
        if task_id is None:
            raise RuntimeError("WebODM did not return a task id")
        logger.info("WebODM create_task success: job_id=%s task_id=%s", job_id, task_id)
        return str(task_id)

    @staticmethod
    def _nodeodm_options_payload(options: dict[str, Any] | None) -> str:
        if not options:
            return "[]"
        payload = []
        for name, value in options.items():
            if value is None:
                continue
            payload.append({"name": str(name), "value": value})
        return json.dumps(payload)

    async def _create_task_nodeodm(
        self,
        *,
        job_id: int,
        options: dict[str, Any] | None,
        resolved_images: list[Path],
    ) -> str:
        url = f"{self.base_url}/task/new"
        data = {
            "name": f"mapping-job-{job_id}",
            "options": self._nodeodm_options_payload(options),
        }

        with ExitStack() as stack:
            files = []
            for image in resolved_images:
                fh = stack.enter_context(image.open("rb"))
                mime_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
                files.append(("images", (image.name, fh, mime_type)))

            async with httpx.AsyncClient(timeout=self.http_timeout_s) as client:
                resp = await client.post(
                    url,
                    params=self._nodeodm_auth_params(),
                    data=data,
                    files=files,
                )
                resp.raise_for_status()
                payload = resp.json()

        task_id = payload.get("uuid")
        if task_id is None:
            error = payload.get("error")
            if error:
                raise RuntimeError(f"NodeODM task creation failed: {error}")
            raise RuntimeError("NodeODM did not return a task uuid")
        logger.info("NodeODM create_task success: job_id=%s task_id=%s", job_id, task_id)
        return str(task_id)

