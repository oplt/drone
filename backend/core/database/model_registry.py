"""Register all module-owned ORM mappings with the shared SQLAlchemy base."""

from __future__ import annotations

from importlib import import_module

_MODEL_MODULES = (
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
    "backend.modules.patrol.models",
    "backend.modules.property_patrol.models",
    "backend.modules.preflight.models",
    "backend.modules.settings.models",
    "backend.modules.telemetry.models",
    "backend.modules.warehouse.models",
    "backend.modules.video_analysis.models",
)
_registered = False


def register_models() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    for module_name in _MODEL_MODULES:
        import_module(module_name)
