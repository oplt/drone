from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.core.logging.paths import legacy_runtime_log_roots, runtime_log_root

TEXT_LOG_SUFFIXES = {".log", ".txt", ".json", ".jsonl", ".out", ".err"}
MAX_FILES_DEFAULT = 80
MAX_FILE_BYTES_DEFAULT = 5 * 1024 * 1024
MAX_BUNDLE_BYTES_DEFAULT = 25 * 1024 * 1024


@dataclass(frozen=True)
class RuntimeLogFile:
    source: str
    path: Path
    relative_path: str
    size_bytes: int
    modified_at: str
    legacy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "legacy": self.legacy,
        }


@dataclass(frozen=True)
class DiagnosticsBundle:
    filename: str
    data: bytes
    content_type: str = "application/zip"


def _utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).replace(microsecond=0).isoformat()


def _safe_source_name(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return "unknown"
    return relative.parts[0] if len(relative.parts) > 1 else "backend"


def _iter_log_files(root: Path, *, legacy: bool = False) -> list[RuntimeLogFile]:
    resolved_root = root.resolve()
    if not resolved_root.exists() or not resolved_root.is_dir():
        return []

    files: list[RuntimeLogFile] = []
    for path in resolved_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_LOG_SUFFIXES:
            continue
        try:
            stat = path.stat()
            relative = path.relative_to(resolved_root).as_posix()
        except OSError:
            continue
        files.append(
            RuntimeLogFile(
                source=_safe_source_name(path, resolved_root),
                path=path,
                relative_path=relative,
                size_bytes=stat.st_size,
                modified_at=_utc_iso(stat.st_mtime),
                legacy=legacy,
            )
        )
    return files


def list_latest_runtime_logs(
    *, limit: int = 50, include_legacy: bool = True
) -> list[RuntimeLogFile]:
    files = _iter_log_files(runtime_log_root())
    if include_legacy:
        for root in legacy_runtime_log_roots():
            if root == runtime_log_root():
                continue
            files.extend(_iter_log_files(root, legacy=True))
    return sorted(files, key=lambda item: item.modified_at, reverse=True)[: max(1, limit)]


def build_diagnostics_bundle(
    *,
    max_files: int = MAX_FILES_DEFAULT,
    max_file_bytes: int = MAX_FILE_BYTES_DEFAULT,
    max_bundle_bytes: int = MAX_BUNDLE_BYTES_DEFAULT,
    include_legacy: bool = True,
) -> DiagnosticsBundle:
    now = datetime.now(UTC).replace(microsecond=0)
    latest_logs = list_latest_runtime_logs(limit=max_files, include_legacy=include_legacy)
    manifest: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "runtime_log_root": str(runtime_log_root()),
        "legacy_roots_included": [str(root) for root in legacy_runtime_log_roots()]
        if include_legacy
        else [],
        "files": [],
        "skipped": [],
    }
    total_bytes = 0
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for log_file in latest_logs:
            if log_file.size_bytes > max_file_bytes:
                manifest["skipped"].append(
                    {
                        "relative_path": log_file.relative_path,
                        "reason": "file_too_large",
                        "size_bytes": log_file.size_bytes,
                    }
                )
                continue
            if total_bytes + log_file.size_bytes > max_bundle_bytes:
                manifest["skipped"].append(
                    {
                        "relative_path": log_file.relative_path,
                        "reason": "bundle_size_limit",
                        "size_bytes": log_file.size_bytes,
                    }
                )
                continue
            try:
                data = log_file.path.read_bytes()
            except OSError:
                manifest["skipped"].append(
                    {"relative_path": log_file.relative_path, "reason": "read_failed"}
                )
                continue

            prefix = "legacy" if log_file.legacy else "runtime"
            archive_name = f"{prefix}/{log_file.source}/{Path(log_file.relative_path).name}"
            archive.writestr(archive_name, data)
            total_bytes += len(data)
            manifest["files"].append({**log_file.to_dict(), "archive_path": archive_name})

        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

    filename = f"drone-diagnostics-{now.strftime('%Y%m%dT%H%M%SZ')}.zip"
    return DiagnosticsBundle(filename=filename, data=buffer.getvalue())
