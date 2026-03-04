from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
logger = logging.getLogger(__name__)


class DroneSyncIngestService:
    """
    Collect geotagged images from a configured sync directory into mapping inputs.

    This supports ground-station / LTE sync workflows where images are copied
    to a shared location before processing starts.
    """

    def __init__(self) -> None:
        self.inputs_root = Path(
            os.getenv("PHOTOGRAMMETRY_INPUTS_DIR", "backend/storage/mapping_jobs_inputs")
        ).resolve()
        self.sync_root = Path(
            os.getenv("PHOTOGRAMMETRY_DRONE_SYNC_DIR", "backend/storage/drone_sync")
        ).resolve()
        self.allow_absolute_source = os.getenv(
            "PHOTOGRAMMETRY_DRONE_SYNC_ALLOW_ABSOLUTE_SOURCE", "0"
        ).lower() in {"1", "true", "yes"}
        self.inputs_root.mkdir(parents=True, exist_ok=True)

    def collect_images_for_job(
        self,
        *,
        job_id: int,
        field_id: int,
        params: Dict[str, Any] | None,
    ) -> List[str]:
        logger.info(
            "Ingest start: job_id=%s field_id=%s input_root=%s sync_root=%s",
            job_id,
            field_id,
            self.inputs_root,
            self.sync_root,
        )
        cfg = (params or {}).get("drone_sync")
        cfg = cfg if isinstance(cfg, dict) else {}

        source_dir = self._resolve_source_dir(
            source_dir=cfg.get("source_dir"),
            field_id=field_id,
            job_id=job_id,
        )
        if source_dir is None:
            logger.error(
                "Ingest failed: no source directory found for job_id=%s field_id=%s",
                job_id,
                field_id,
            )
            raise RuntimeError(
                "No drone-sync image source found. Configure PHOTOGRAMMETRY_DRONE_SYNC_DIR "
                "or provide drone_sync.source_dir in mapping job payload."
            )
        logger.info("Ingest source resolved: job_id=%s source_dir=%s", job_id, source_dir)

        recursive = bool(cfg.get("recursive", True))
        image_paths = self._list_images(source_dir, recursive=recursive)
        if not image_paths:
            logger.error(
                "Ingest failed: source directory has no images. job_id=%s source_dir=%s",
                job_id,
                source_dir,
            )
            raise RuntimeError(f"No geotagged images found in drone sync source: {source_dir}")

        job_dir = self.inputs_root / str(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        rel_paths: List[str] = []
        for src in image_paths:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            safe_name = f"{stamp}_{src.name}"
            dst = job_dir / safe_name
            shutil.copy2(src, dst)
            rel_paths.append(str(dst.relative_to(self.inputs_root)))
        logger.info(
            "Ingest completed: job_id=%s copied_images=%s destination=%s",
            job_id,
            len(rel_paths),
            job_dir,
        )
        return rel_paths

    def _resolve_source_dir(
        self, *, source_dir: Any, field_id: int, job_id: int
    ) -> Path | None:
        candidates: List[Path] = []
        if isinstance(source_dir, str) and source_dir.strip():
            raw = source_dir.strip()
            src = Path(raw)
            if src.is_absolute():
                if not self.allow_absolute_source:
                    raise RuntimeError(
                        "Absolute drone sync source_dir is disabled by "
                        "PHOTOGRAMMETRY_DRONE_SYNC_ALLOW_ABSOLUTE_SOURCE=0"
                    )
                candidates.append(src)
            else:
                if ".." in Path(raw).parts:
                    raise RuntimeError("Invalid drone sync source_dir path traversal.")
                candidates.append((self.sync_root / raw).resolve())
        else:
            candidates.extend(
                [
                    (self.sync_root / f"field_{field_id}").resolve(),
                    (self.sync_root / str(field_id)).resolve(),
                    (self.sync_root / f"job_{job_id}").resolve(),
                    (self.sync_root / str(job_id)).resolve(),
                    (self.sync_root / f"flight_{field_id}").resolve(),
                    (self.sync_root / f"flight_{job_id}").resolve(),
                ]
            )

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                if self._list_images(candidate, recursive=True):
                    logger.info("Ingest candidate selected: %s", candidate)
                    return candidate
        logger.warning(
            "No ingest candidate with images found. candidates=%s",
            [str(c) for c in candidates],
        )
        return None

    @staticmethod
    def _list_images(source_dir: Path, *, recursive: bool) -> Sequence[Path]:
        walker = source_dir.rglob("*") if recursive else source_dir.glob("*")
        files = [
            p
            for p in walker
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ]
        return sorted(files)
