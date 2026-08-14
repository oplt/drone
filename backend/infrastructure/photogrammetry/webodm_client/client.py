from __future__ import annotations

from backend.infrastructure.photogrammetry.webodm_client.backend_detection import BackendDetectionMixin
from backend.infrastructure.photogrammetry.webodm_client.client_core import ClientCoreMixin
from backend.infrastructure.photogrammetry.webodm_client.download import DownloadMixin
from backend.infrastructure.photogrammetry.webodm_client.inputs_retry import InputsRetryMixin
from backend.infrastructure.photogrammetry.webodm_client.outputs import OutputsMixin
from backend.infrastructure.photogrammetry.webodm_client.task_create import TaskCreateMixin
from backend.infrastructure.photogrammetry.webodm_client.task_status import TaskStatusMixin


class WebODMClient(
    ClientCoreMixin,
    BackendDetectionMixin,
    InputsRetryMixin,
    TaskCreateMixin,
    TaskStatusMixin,
    DownloadMixin,
    OutputsMixin,
):
    """
    Async WebODM / NodeODM client for task orchestration and output retrieval.

    Modes:
    - Mock mode: reads local canned outputs
    - Live mode: uploads images, monitors task, downloads all.zip outputs
    """
