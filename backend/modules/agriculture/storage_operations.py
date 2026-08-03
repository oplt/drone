"""Operational checks and non-destructive storage verification helpers."""

from __future__ import annotations

import hashlib
import uuid
from contextlib import suppress
from typing import Any

from backend.core.config.runtime import settings
from backend.modules.agriculture.storage import agriculture_storage


def storage_readiness() -> dict[str, Any]:
    """Return actionable storage checks without exposing credentials or object keys."""
    checks: list[dict[str, Any]] = []
    backend = str(getattr(settings, "storage_backend", "local")).lower()
    checks.append(
        {
            "code": "backend_configured",
            "status": "pass" if backend in {"local", "s3"} else "block",
            "observed": backend,
        }
    )
    checks.append(
        {
            "code": "malware_scan_required",
            "status": "pass"
            if backend != "s3"
            or bool(getattr(settings, "agriculture_malware_scan_required", False))
            else "block",
            "observed": bool(getattr(settings, "agriculture_malware_scan_required", False)),
        }
    )
    checks.append(
        {
            "code": "signed_delivery_tls",
            "status": "pass"
            if backend != "s3" or bool(getattr(agriculture_storage, "require_tls", True))
            else "block",
            "observed": bool(getattr(agriculture_storage, "require_tls", True)),
        }
    )
    try:
        healthy, latency_ms = agriculture_storage.health()
        checks.append(
            {
                "code": "object_store_reachable",
                "status": "pass" if healthy else "block",
                "latency_ms": latency_ms,
            }
        )
    except Exception as exc:
        checks.append(
            {"code": "object_store_reachable", "status": "block", "reason": type(exc).__name__}
        )
    try:
        agriculture_storage.validate_key("org/7/backups/agriculture/readiness-check")
        checks.append({"code": "backup_prefix_valid", "status": "pass"})
    except ValueError as exc:
        checks.append({"code": "backup_prefix_valid", "status": "block", "reason": str(exc)})
    blocked = [check["code"] for check in checks if check["status"] == "block"]
    return {
        "status": "blocked" if blocked else "ready",
        "backend": backend,
        "checks": checks,
        "blocked_checks": blocked,
    }


def local_restore_drill() -> dict[str, Any]:
    """Verify write/backup/delete/restore/checksum behavior using a private drill object."""
    if not hasattr(agriculture_storage, "backup") or not hasattr(agriculture_storage, "restore"):
        return {"status": "blocked", "reason": "storage_adapter_missing_lifecycle_operations"}
    token = uuid.uuid4().hex
    key = f"org/0/operations/drill/{token}.bin"
    backup_key = f"org/0/backups/agriculture/drill/{token}.bin"
    payload = f"agriculture-restore-drill:{token}".encode()
    checksum = hashlib.sha256(payload).hexdigest()
    try:
        agriculture_storage.validate_tenant_key(key, org_id=0, resource="operations/drill")
        agriculture_storage.write_object(key, payload, expected_checksum=checksum)
        agriculture_storage.backup(key, backup_key=backup_key)
        agriculture_storage.delete(key)
        agriculture_storage.restore(backup_key, target_key=key, expected_checksum=checksum)
        verified = agriculture_storage.exists(key) and agriculture_storage.checksum(key) == checksum
        return {"status": "pass" if verified else "fail", "checksum_verified": verified}
    except Exception as exc:
        return {"status": "fail", "checksum_verified": False, "reason": type(exc).__name__}
    finally:
        for candidate in (key, backup_key):
            with suppress(Exception):
                agriculture_storage.delete(candidate)
