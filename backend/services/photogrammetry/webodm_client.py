from __future__ import annotations

import json
import mimetypes
import os
import shutil
import zipfile
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class WebODMClient:
    """
    Async WebODM client for task orchestration and output retrieval.

    Modes:
    - Mock mode: reads local canned outputs
    - Live mode: uploads images, monitors task, downloads all.zip outputs
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("WEBODM_BASE_URL", "http://localhost:8001").rstrip("/")
        self.api_token = os.getenv("WEBODM_API_TOKEN", "")
        self.project_id = int(os.getenv("WEBODM_PROJECT_ID", "1"))
        self.mock_mode = os.getenv("WEBODM_MOCK_MODE", "0").lower() in {"1", "true", "yes"}
        self.mock_outputs_dir = Path(
            os.getenv("WEBODM_MOCK_OUTPUTS_DIR", "backend/mock/webodm_outputs")
        ).resolve()

        self.inputs_root = Path(
            os.getenv("PHOTOGRAMMETRY_INPUTS_DIR", "backend/storage/mapping_jobs_inputs")
        ).resolve()
        self.downloads_root = _ensure_dir(
            Path(os.getenv("PHOTOGRAMMETRY_WEBODM_DOWNLOADS_DIR", "backend/storage/webodm_downloads")).resolve()
        )
        self.http_timeout_s = float(os.getenv("WEBODM_HTTP_TIMEOUT_S", "120"))
        self.download_all_endpoint_template = os.getenv(
            "WEBODM_DOWNLOAD_ALL_ENDPOINT_TEMPLATE",
            "/api/projects/{project_id}/tasks/{task_id}/download/all.zip",
        )

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_token:
            headers["Authorization"] = f"JWT {self.api_token}"
        return headers

    def _resolve_image_paths(self, image_paths: Optional[Iterable[str]]) -> List[Path]:
        resolved: List[Path] = []
        for raw in image_paths or []:
            s = str(raw).strip()
            if not s:
                continue
            p = Path(s)
            if not p.is_absolute():
                p = (self.inputs_root / p).resolve()
            else:
                p = p.resolve()
            if not p.exists() or not p.is_file():
                raise FileNotFoundError(f"WebODM input image not found: {p}")
            resolved.append(p)
        if not resolved:
            raise RuntimeError("WebODM task requires at least one input image.")
        return resolved

    async def create_task(
        self,
        *,
        job_id: int,
        options: Dict[str, Any] | None = None,
        image_paths: list[str] | None = None,
    ) -> str:
        if self.mock_mode:
            return f"mock-{job_id}"

        resolved_images = self._resolve_image_paths(image_paths)
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
        return str(task_id)

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        if self.mock_mode:
            return {"state": "COMPLETED", "progress": 100}

        url = f"{self.base_url}/api/projects/{self.project_id}/tasks/{task_id}/"
        async with httpx.AsyncClient(timeout=self.http_timeout_s) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()

        raw_status = payload.get("status")
        status_str = str(raw_status).lower()
        if isinstance(raw_status, int) or status_str.isdigit():
            status_code = int(raw_status)
        else:
            status_code = None

        # WebODM status codes: 10 queued, 20 running, 30 failed, 40 completed, 50 canceled.
        if status_code == 40 or status_str in {"completed", "done", "ready"}:
            state = "COMPLETED"
        elif status_code in {30, 50} or status_str in {"failed", "error", "canceled"}:
            state = "FAILED"
        else:
            state = "RUNNING"

        raw_progress = payload.get("running_progress", payload.get("progress", 0))
        try:
            progress = int(float(raw_progress))
        except Exception:
            progress = 0
        progress = max(0, min(100, progress))

        result: Dict[str, Any] = {
            "state": state,
            "progress": progress,
        }
        if state == "FAILED":
            result["error"] = payload.get("last_error") or payload.get("error")
        return result

    async def download_outputs(self, task_id: str) -> Dict[str, str]:
        if self.mock_mode:
            return self._mock_outputs()

        task_dir = _ensure_dir(
            self.downloads_root / f"task_{task_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        )
        archive_path = task_dir / "all.zip"
        extract_dir = _ensure_dir(task_dir / "extracted")
        await self._download_all_archive(task_id=task_id, destination=archive_path)
        self._extract_archive(archive_path=archive_path, destination=extract_dir)
        outputs = self._locate_outputs(extract_dir)
        outputs["__download_root"] = str(task_dir)
        return outputs

    async def _download_all_archive(self, *, task_id: str, destination: Path) -> None:
        endpoint = self.download_all_endpoint_template.format(
            project_id=self.project_id,
            task_id=task_id,
        )
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers=self._headers()) as resp:
                resp.raise_for_status()
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as f:
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            f.write(chunk)

    @staticmethod
    def _extract_archive(*, archive_path: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.infolist():
                target = (destination / member.filename).resolve()
                if not str(target).startswith(str(destination.resolve())):
                    raise RuntimeError(f"Unsafe archive path detected: {member.filename}")
            zf.extractall(destination)

    @staticmethod
    def _first_match(root: Path, patterns: List[str]) -> Optional[Path]:
        for pattern in patterns:
            for item in root.glob(pattern):
                if item.exists() and item.is_file():
                    return item.resolve()
        return None

    def _locate_outputs(self, extracted_root: Path) -> Dict[str, str]:
        ortho = self._first_match(
            extracted_root,
            [
                "**/odm_orthophoto/odm_orthophoto.tif",
                "**/*orthophoto*.tif",
                "**/*orthomosaic*.tif",
            ],
        )
        dsm = self._first_match(
            extracted_root,
            [
                "**/odm_dem/dsm.tif",
                "**/*dsm*.tif",
            ],
        )
        dtm = self._first_match(
            extracted_root,
            [
                "**/odm_dem/dtm.tif",
                "**/*dtm*.tif",
            ],
        )
        mesh = self._first_match(
            extracted_root,
            [
                "**/odm_texturing/*textured*.glb",
                "**/odm_texturing/*textured*.obj",
                "**/*mesh*.glb",
                "**/*mesh*.obj",
            ],
        )
        point_cloud = self._first_match(
            extracted_root,
            [
                "**/*.laz",
                "**/*.las",
            ],
        )

        if not ortho or not dsm or not mesh:
            raise RuntimeError(
                "WebODM export is missing required artifacts (orthophoto, dsm, mesh). "
                f"Located: orthophoto={bool(ortho)}, dsm={bool(dsm)}, mesh={bool(mesh)}"
            )

        outputs: Dict[str, str] = {
            "orthophoto": str(ortho),
            "dsm": str(dsm),
            "mesh": str(mesh),
        }
        if dtm:
            outputs["dtm"] = str(dtm)
        if point_cloud:
            outputs["point_cloud"] = str(point_cloud)
        return outputs

    def _mock_outputs(self) -> Dict[str, str]:
        ortho = self.mock_outputs_dir / "orthophoto.tif"
        dsm = self.mock_outputs_dir / "dsm.tif"
        dtm = self.mock_outputs_dir / "dtm.tif"
        mesh_obj = self.mock_outputs_dir / "mesh.obj"
        mesh_glb = self.mock_outputs_dir / "mesh.glb"
        mesh = mesh_glb if mesh_glb.exists() else mesh_obj
        point_cloud_laz = self.mock_outputs_dir / "point_cloud.laz"
        point_cloud_las = self.mock_outputs_dir / "point_cloud.las"
        point_cloud = (
            point_cloud_laz
            if point_cloud_laz.exists()
            else point_cloud_las
            if point_cloud_las.exists()
            else None
        )

        if not ortho.exists():
            raise FileNotFoundError(f"Mock orthophoto not found: {ortho}")
        if not dsm.exists():
            raise FileNotFoundError(f"Mock DSM not found: {dsm}")
        if not mesh.exists():
            raise FileNotFoundError(
                f"Mock mesh not found (expected mesh.glb or mesh.obj in {self.mock_outputs_dir})"
            )

        outputs: Dict[str, str] = {
            "orthophoto": str(ortho),
            "dsm": str(dsm),
            "mesh": str(mesh),
        }
        if dtm.exists():
            outputs["dtm"] = str(dtm)
        if point_cloud is not None:
            outputs["point_cloud"] = str(point_cloud)
        return outputs
