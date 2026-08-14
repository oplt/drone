from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from backend.infrastructure.photogrammetry.webodm_client.paths import _ensure_dir

logger = logging.getLogger(__name__)


class DownloadMixin:
    """Archive download and extraction orchestration."""

    async def download_outputs(self, task_id: str) -> dict[str, str]:
        if self.mock_mode:
            logger.info("WebODM download_outputs mock mode: task_id=%s", task_id)
            return self._mock_outputs()

        task_dir = _ensure_dir(
            self.downloads_root / f"task_{task_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        )
        logger.info(
            "WebODM download_outputs start: task_id=%s destination=%s",
            task_id,
            task_dir,
        )
        archive_path = task_dir / "all.zip"
        extract_dir = _ensure_dir(task_dir / "extracted")
        await self._download_all_archive(task_id=task_id, destination=archive_path)
        await asyncio.to_thread(
            self._extract_archive,
            archive_path=archive_path,
            destination=extract_dir,
        )
        outputs = await asyncio.to_thread(self._locate_outputs, extract_dir)
        outputs["__download_root"] = str(task_dir)
        logger.info(
            "WebODM download_outputs success: task_id=%s outputs=%s",
            task_id,
            sorted(outputs.keys()),
        )
        return outputs

    async def _download_all_archive(self, *, task_id: str, destination: Path) -> None:
        backend_kind = await self._get_backend_kind()
        if backend_kind == "nodeodm":
            url = f"{self.base_url}/task/{task_id}/download/all.zip"
            request_headers = {}
            request_params = self._nodeodm_auth_params()
        else:
            endpoint = self.download_all_endpoint_template.format(
                project_id=self.project_id,
                task_id=task_id,
            )
            if not endpoint.startswith("/"):
                endpoint = f"/{endpoint}"
            url = f"{self.base_url}{endpoint}"
            request_headers = self._headers()
            request_params: dict[str, str] = {}
        logger.info(
            "WebODM archive download start: task_id=%s url=%s destination=%s",
            task_id,
            url,
            destination,
        )

        async def _download_once() -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination.unlink()
            async with (
                httpx.AsyncClient(timeout=None, follow_redirects=True) as client,
                client.stream(
                    "GET",
                    url,
                    headers=request_headers,
                    params=request_params,
                ) as resp,
            ):
                    resp.raise_for_status()
                    with destination.open("wb") as f:
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                f.write(chunk)

        await self._run_with_retry(
            f"download_outputs_archive(task_id={task_id})",
            _download_once,
        )
        logger.info(
            "WebODM archive download finished: task_id=%s bytes=%s",
            task_id,
            destination.stat().st_size if destination.exists() else 0,
        )

