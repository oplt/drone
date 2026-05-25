from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from backend.infrastructure.photogrammetry.raster_tiling import (
    convert_mesh_to_3dtiles,
    convert_to_cog,
    generate_xyz_tiles,
    inspect_raster_georeferencing,
)

logger = logging.getLogger(__name__)


def convert_outputs(
    self,
    outputs: dict[str, str],
    work_dir: Path,
    *,
    requested_artifacts: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    work_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Photogrammetry conversion started: work_dir=%s requested_artifacts=%s",
        work_dir,
        requested_artifacts or {},
    )

    converted: dict[str, str] = {}
    artifact_meta: dict[str, dict[str, Any]] = {}

    requested_artifacts = requested_artifacts or {}

    def enabled(name: str, default: bool) -> bool:
        val = requested_artifacts.get(name)
        if val is None:
            return default
        return bool(val)

    ortho_enabled = enabled("orthomosaic", True)
    dsm_enabled = enabled("dsm", True)
    dtm_enabled = enabled("dtm", False)
    mesh_enabled = enabled("textured_mesh", True)
    xyz_enabled = enabled("xyz_tiles", True)
    point_cloud_enabled = enabled("point_cloud", False)

    ortho_src = outputs.get("orthophoto")
    dsm_src = outputs.get("dsm")
    dtm_src = outputs.get("dtm")
    ortho_cog: str | None = None
    mesh_georef: dict[str, Any] | None = None
    ortho_georef: dict[str, Any] | None = None
    dsm_georef: dict[str, Any] | None = None
    dtm_georef: dict[str, Any] | None = None

    if ortho_src and (ortho_enabled or mesh_enabled):
        ortho_georef = inspect_raster_georeferencing(ortho_src)
    if dsm_src and (dsm_enabled or mesh_enabled):
        dsm_georef = inspect_raster_georeferencing(dsm_src)
    if dtm_src and (dtm_enabled or mesh_enabled):
        dtm_georef = inspect_raster_georeferencing(dtm_src)

    for candidate in (ortho_georef, dsm_georef, dtm_georef):
        if isinstance(candidate, dict) and candidate.get("validated"):
            mesh_georef = candidate
            break

    if ortho_enabled:
        if not ortho_src:
            raise RuntimeError("WebODM output missing required orthophoto")
        ortho_cog = convert_to_cog(ortho_src, str(work_dir / "orthomosaic.cog.tif"))
        converted["orthomosaic_cog"] = ortho_cog
        artifact_meta["orthomosaic_cog"] = {
            "georef": ortho_georef,
            "source": "orthophoto",
        }
        logger.info("Converted orthomosaic COG: %s", ortho_cog)

    if dsm_enabled:
        if not dsm_src:
            raise RuntimeError("WebODM output missing required DSM")
        dsm_cog = convert_to_cog(dsm_src, str(work_dir / "dsm.cog.tif"))
        converted["dsm_cog"] = dsm_cog
        artifact_meta["dsm_cog"] = {
            "georef": dsm_georef,
            "source": "dsm",
        }
        logger.info("Converted DSM COG: %s", dsm_cog)

    if dtm_enabled:
        if dtm_src:
            dtm_cog = convert_to_cog(dtm_src, str(work_dir / "dtm.cog.tif"))
            converted["dtm_cog"] = dtm_cog
            artifact_meta["dtm_cog"] = {
                "georef": dtm_georef,
                "source": "dtm",
            }
            logger.info("Converted DTM COG: %s", dtm_cog)
        else:
            logger.warning("DTM requested but not available in WebODM outputs")

    if xyz_enabled and ortho_cog:
        # Optional XYZ for mobile/offline map use.
        xyz_dir = generate_xyz_tiles(ortho_cog, str(work_dir / "orthomosaic_xyz"))
        if xyz_dir:
            converted["orthomosaic_xyz"] = xyz_dir
            artifact_meta["orthomosaic_xyz"] = {
                "source": "orthomosaic_cog",
                "format": "xyz",
            }
            logger.info("Generated XYZ tiles: %s", xyz_dir)

    if mesh_enabled:
        mesh_src = outputs.get("mesh")
        if not mesh_src:
            raise RuntimeError("WebODM output missing required mesh")
        tileset_dir = convert_mesh_to_3dtiles(
            mesh_src,
            str(work_dir / "mesh_3dtiles"),
            georef=mesh_georef,
        )
        converted["textured_mesh_3dtiles"] = tileset_dir
        artifact_meta["textured_mesh_3dtiles"] = {
            "source": "mesh",
            "format": "3dtiles",
            "georef": mesh_georef,
            "bbox_wgs84": (
                mesh_georef.get("bbox_wgs84") if isinstance(mesh_georef, dict) else None
            ),
        }
        logger.info("Generated textured mesh 3D tiles: %s", tileset_dir)

    if point_cloud_enabled:
        point_cloud_src = outputs.get("point_cloud")
        if point_cloud_src:
            src = Path(point_cloud_src).resolve()
            dst = work_dir / src.name
            if src != dst:
                shutil.copy2(src, dst)
            converted["point_cloud"] = str(dst)
            artifact_meta["point_cloud"] = {
                "source": "point_cloud",
                "ext": dst.suffix.lower(),
            }
            logger.info("Prepared point cloud artifact: %s", dst)
        else:
            logger.warning("Point cloud requested but not available in WebODM outputs")

    logger.info(
        "Photogrammetry conversion finished: converted=%s",
        sorted(converted.keys()),
    )
    return converted, artifact_meta
