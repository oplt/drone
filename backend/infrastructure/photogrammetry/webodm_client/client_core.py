from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from backend.core.config.runtime import env_truthy, settings
from backend.infrastructure.photogrammetry.webodm_client.paths import _ensure_dir

logger = logging.getLogger(__name__)


class ClientCoreMixin:
    """Client configuration and initialization."""

    def __init__(self) -> None:
        self.base_url = settings.WEBODM_BASE_URL.rstrip("/")
        self.api_token = settings.WEBODM_API_TOKEN
        self.project_id = settings.WEBODM_PROJECT_ID
        self.mock_mode = env_truthy(settings.WEBODM_MOCK_MODE)
        self.mock_outputs_dir = Path(settings.webodm_mock_outputs_dir).resolve()

        self.inputs_root = Path(settings.PHOTOGRAMMETRY_INPUTS_DIR).resolve()
        self.downloads_root = _ensure_dir(
            Path(settings.photogrammetry_webodm_downloads_dir).resolve()
        )
        self.http_timeout_s = settings.webodm_http_timeout_s
        self.http_retry_attempts = settings.webodm_http_retry_attempts
        self.http_retry_min_delay_s = settings.webodm_http_retry_min_delay_s
        self.http_retry_max_delay_s = settings.webodm_http_retry_max_delay_s
        self.http_retry_backoff_factor = settings.webodm_http_retry_backoff_factor
        if self.http_retry_max_delay_s < self.http_retry_min_delay_s:
            logger.warning(
                "WEBODM_HTTP_RETRY_MAX_DELAY_S (%s) is lower than "
                "WEBODM_HTTP_RETRY_MIN_DELAY_S (%s); "
                "using min delay for both.",
                self.http_retry_max_delay_s,
                self.http_retry_min_delay_s,
            )
            self.http_retry_max_delay_s = self.http_retry_min_delay_s
        self.upload_batch_size = settings.webodm_upload_batch_size
        self.download_all_endpoint_template = settings.webodm_download_all_endpoint_template
        configured_backend = settings.photogrammetry_processor_backend.strip().lower()
        if configured_backend not in {"auto", "webodm", "nodeodm"}:
            logger.warning(
                "Invalid PHOTOGRAMMETRY_PROCESSOR_BACKEND=%r; expected auto|webodm|nodeodm. "
                "Falling back to auto.",
                configured_backend,
            )
            configured_backend = "auto"
        self.processor_backend: Literal["auto", "webodm", "nodeodm"] = configured_backend  # type: ignore[assignment]
        self._detected_backend: Literal["webodm", "nodeodm"] | None = None
        logger.info(
            "Photogrammetry client initialized: base_url=%s project_id=%s "
            "mock_mode=%s configured_backend=%s",
            self.base_url,
            self.project_id,
            self.mock_mode,
            self.processor_backend,
        )

