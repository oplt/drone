from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from backend.core.config.runtime import settings

logger = logging.getLogger(__name__)


class BackendDetectionMixin:
    """Backend kind detection and auth helpers."""

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_token:
            headers["Authorization"] = f"JWT {self.api_token}"
        return headers

    def _nodeodm_auth_params(self) -> dict[str, str]:
        if not self.api_token:
            return {}
        return {"token": self.api_token}

    @staticmethod
    def _looks_like_jwt_token(token: str) -> bool:
        stripped = token.strip()
        return stripped.count(".") == 2 and " " not in stripped

    @staticmethod
    def _looks_like_uuid_token(token: str) -> bool:
        stripped = token.strip()
        return len(stripped) == 36 and stripped.count("-") == 4 and " " not in stripped

    @staticmethod
    def _looks_like_nodeodm_info(payload: Any) -> bool:
        return (
            isinstance(payload, dict)
            and "version" in payload
            and (
                "taskQueueCount" in payload or "engineVersion" in payload or "maxImages" in payload
            )
        )

    async def _get_backend_kind(self) -> Literal["webodm", "nodeodm"]:
        if self.processor_backend in {"webodm", "nodeodm"}:
            return self.processor_backend
        if self._detected_backend is not None:
            return self._detected_backend
        self._detected_backend = await self._detect_backend_kind()
        return self._detected_backend

    async def _detect_backend_kind(self) -> Literal["webodm", "nodeodm"]:
        info_url = f"{self.base_url}/info"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout_s) as client:
                resp = await client.get(
                    info_url,
                    params=self._nodeodm_auth_params(),
                )
                if resp.is_success:
                    payload = resp.json()
                    if self._looks_like_nodeodm_info(payload):
                        logger.info(
                            "Detected NodeODM backend: base_url=%s version=%s",
                            self.base_url,
                            payload.get("version"),
                        )
                        return "nodeodm"
        except Exception as exc:
            logger.debug("NodeODM backend probe failed for %s: %s", info_url, exc)

        if self._looks_like_uuid_token(self.api_token) and not self._looks_like_jwt_token(
            self.api_token
        ):
            logger.info(
                "Assuming NodeODM backend for base_url=%s because "
                "WEBODM_API_TOKEN looks like a NodeODM token",
                self.base_url,
            )
            return "nodeodm"

        logger.info("Defaulting to WebODM backend for base_url=%s", self.base_url)
        return "webodm"

