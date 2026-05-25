from __future__ import annotations

from backend.infrastructure.photogrammetry.ingest import DroneSyncIngestService
from backend.infrastructure.photogrammetry.storage import StorageService
from backend.infrastructure.photogrammetry.webodm_client import WebODMClient
from backend.modules.mapping.job import MappingProcessingJob
from backend.modules.mapping.service.workflow import PhotogrammetryService
from backend.modules.settings.repository import SettingsRepository
from backend.modules.settings.service import get_runtime_settings


def build_photogrammetry_service() -> PhotogrammetryService:
    return PhotogrammetryService(WebODMClient(), StorageService(), DroneSyncIngestService())


def build_mapping_job() -> MappingProcessingJob:
    async def load_runtime_settings() -> object:
        return await get_runtime_settings(SettingsRepository())

    return MappingProcessingJob(build_photogrammetry_service(), before_run=load_runtime_settings)
