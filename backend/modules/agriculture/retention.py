"""Conservative retention helper for local development and scheduled workers."""

from datetime import UTC, datetime, timedelta
from pathlib import Path


def expired_local_assets(root: str | Path, *, older_than_days: int = 30) -> list[Path]:
    cutoff = datetime.now(UTC) - timedelta(days=max(1, older_than_days))
    base = Path(root).resolve()
    if not base.is_dir():
        return []
    return [
        path for path in base.rglob("*")
        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) < cutoff
    ]
