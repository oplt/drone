from __future__ import annotations

from typing import Any

import httpx


class TaskStatusMixin:
    """Task status polling and normalization."""

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        if self.mock_mode:
            return {"state": "COMPLETED", "progress": 100}

        backend_kind = await self._get_backend_kind()
        if backend_kind == "nodeodm":
            return await self._get_task_status_nodeodm(task_id)
        return await self._get_task_status_webodm(task_id)

    async def _get_task_status_webodm(self, task_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/projects/{self.project_id}/tasks/{task_id}/"

        async def _fetch_status() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=self.http_timeout_s) as client:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                return resp.json()

        payload = await self._run_with_retry(
            f"get_task_status(task_id={task_id})",
            _fetch_status,
        )

        return self._normalize_task_status(payload)

    async def _get_task_status_nodeodm(self, task_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/task/{task_id}/info"

        async def _fetch_status() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=self.http_timeout_s) as client:
                resp = await client.get(url, params=self._nodeodm_auth_params())
                resp.raise_for_status()
                return resp.json()

        payload = await self._run_with_retry(
            f"get_task_status(task_id={task_id})",
            _fetch_status,
        )

        return self._normalize_task_status(payload)

    @staticmethod
    def _status_code(raw_status: Any) -> int | None:
        if isinstance(raw_status, dict):
            raw_status = raw_status.get("code", raw_status.get("status"))
        status_str = str(raw_status).lower()
        if isinstance(raw_status, int) or status_str.isdigit():
            return int(raw_status)
        return None

    @classmethod
    def _normalize_task_status(cls, payload: dict[str, Any]) -> dict[str, Any]:
        raw_status = payload.get("status")
        status_code = cls._status_code(raw_status)
        status_str = str(raw_status).lower()

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

        result: dict[str, Any] = {
            "state": state,
            "progress": progress,
        }
        if state == "FAILED":
            result["error"] = payload.get("last_error") or payload.get("error")
        return result

