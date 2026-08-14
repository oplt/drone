from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)
T = TypeVar("T")


class InputsRetryMixin:
    """Input resolution and HTTP retry helpers."""

    def _resolve_image_paths(self, image_paths: Iterable[str] | None) -> list[Path]:
        resolved: list[Path] = []
        for raw in image_paths or []:
            s = str(raw).strip()
            if not s:
                continue
            p = Path(s)
            p = (self.inputs_root / p).resolve() if not p.is_absolute() else p.resolve()
            if not p.exists() or not p.is_file():
                raise FileNotFoundError(f"WebODM input image not found: {p}")
            resolved.append(p)
        if not resolved:
            raise RuntimeError("WebODM task requires at least one input image.")
        return resolved

    @staticmethod
    def _is_retryable_http_exception(exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code if exc.response is not None else None
            return status in {408, 429, 500, 502, 503, 504}
        return False

    async def _run_with_retry(
        self,
        op_name: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        attempt = 1
        while True:
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt >= self.http_retry_attempts or not self._is_retryable_http_exception(
                    exc
                ):
                    raise
                delay = min(
                    self.http_retry_min_delay_s * (self.http_retry_backoff_factor ** (attempt - 1)),
                    self.http_retry_max_delay_s,
                )
                delay = min(self.http_retry_max_delay_s, delay * random.uniform(0.8, 1.2))
                logger.warning(
                    "WebODM %s failed (attempt %s/%s): %s. Retrying in %.1fs",
                    op_name,
                    attempt,
                    self.http_retry_attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

