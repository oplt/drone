"""Register all module-owned ORM mappings with the shared SQLAlchemy base."""

from __future__ import annotations

import logging
import threading
from importlib import import_module

logger = logging.getLogger(__name__)

_MODEL_MODULES = (
    "backend.modules.agents.models",
    "backend.modules.alerts.models",
    "backend.modules.automation.models",
    "backend.modules.compliance.models",
    "backend.modules.deliverables.models",
    "backend.modules.fields.models",
    "backend.modules.fleet.models",
    "backend.modules.geofences.models",
    "backend.modules.identity.models",
    "backend.modules.integrations.webhooks.models",
    "backend.modules.irrigation.models",
    "backend.modules.livestock.models",
    "backend.modules.mapping.models",
    "backend.modules.missions.command_models",
    "backend.modules.missions.flight_models",
    "backend.modules.missions.runtime_models",
    "backend.modules.organizations.models",
    "backend.modules.patrol.config_models",
    "backend.modules.patrol.models",
    "backend.modules.property_patrol.models",
    "backend.modules.preflight.models",
    "backend.modules.settings.models",
    "backend.modules.telemetry.models",
    "backend.modules.warehouse.models",
    "backend.modules.video_analysis.models",
)

_registered = False
_register_lock = threading.RLock()


def register_models() -> None:
    """Import all ORM model modules exactly once.

    The previous implementation marked the registry as complete before imports ran.
    If one import failed, later calls became no-ops and SQLAlchemy metadata stayed
    partially registered. This function now marks registration complete only after
    every module imports successfully and is safe to call from concurrent startup
    paths.
    """
    global _registered

    if _registered:
        return

    with _register_lock:
        if _registered:
            return

        for module_name in _MODEL_MODULES:
            import_module(module_name)
            logger.debug("Registered ORM model module %s", module_name)

        _registered = True
