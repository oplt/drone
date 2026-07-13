"""Production-only configuration safety checks."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

_PRODUCTION_ENVS = {"prod", "production", "staging"}
_KNOWN_DEV_SECRETS = {
    "local-dev-secret-change-me",
    "drone-live-map-ingest",
    "dev-live-map-ingest",
    "minioadmin",
    "drone",
    "replace-with-a-long-random-secret",
    "replace-me",
    "dev-placeholder",
    "local-test-secret-change-me",
    "replace-with-a-local-password",
    "replace-with-a-local-user",
}


def is_production_environment(settings: Any) -> bool:
    return str(getattr(settings, "app_env", "local")).strip().lower() in _PRODUCTION_ENVS


def validate_production_security(settings: Any, bootstrap: Any | None = None) -> None:
    """Reject known development credentials before serving production traffic."""
    if not is_production_environment(settings):
        return

    failures: list[str] = []
    values = {
        "JWT_SECRET": getattr(settings, "jwt_secret", ""),
        "WAREHOUSE_LIVE_MAP_INGEST_TOKEN": getattr(
            settings, "warehouse_live_map_ingest_token", ""
        ),
        "GOOGLE_MAPS_API_KEY": getattr(settings, "google_maps_api_key", ""),
        "RASPBERRY_PASSWORD": getattr(settings, "raspberry_password", ""),
        "PHOTOGRAMMETRY_ASSET_SIGNING_SECRET": getattr(
            settings, "PHOTOGRAMMETRY_ASSET_SIGNING_SECRET", ""
        ),
    }
    if str(getattr(settings, "storage_backend", "local")).lower() == "s3":
        values["S3_ACCESS_KEY"] = getattr(settings, "s3_access_key", "")
        values["S3_SECRET_KEY"] = getattr(settings, "s3_secret_key", "")

    for name, value in values.items():
        normalized = str(value or "").strip().lower()
        if not normalized or normalized in _KNOWN_DEV_SECRETS:
            failures.append(name)

    database_url = str(getattr(settings, "database_url", ""))
    try:
        password = urlsplit(database_url).password
    except ValueError:
        password = None
    if str(password or "").lower() in {"drone", "change-me", "password"}:
        failures.append("DATABASE_URL password")

    if not bool(getattr(settings, "cookie_secure", False)):
        failures.append("COOKIE_SECURE must be true")
    if bool(getattr(settings, "photogrammetry_public_static_assets", False)):
        failures.append("PHOTOGRAMMETRY_PUBLIC_STATIC_ASSETS must be false")

    vault_key = str(getattr(bootstrap, "settings_vault_key", "") or "")
    if not vault_key:
        failures.append("SETTINGS_VAULT_KEY")

    if failures:
        names = ", ".join(failures)
        raise RuntimeError(f"Production security validation failed: {names}")
