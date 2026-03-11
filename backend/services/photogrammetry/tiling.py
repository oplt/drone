from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _extract_lonlat_pairs(node: object) -> list[tuple[float, float]]:
    if isinstance(node, (list, tuple)):
        if (
            len(node) >= 2
            and isinstance(node[0], (int, float))
            and isinstance(node[1], (int, float))
        ):
            return [(float(node[0]), float(node[1]))]
        out: list[tuple[float, float]] = []
        for child in node:
            out.extend(_extract_lonlat_pairs(child))
        return out
    return []


def _bbox_from_wgs84_extent(wgs84_extent: dict | None) -> dict[str, float] | None:
    if not isinstance(wgs84_extent, dict):
        return None
    direct_keys = {"west", "south", "east", "north"}
    if direct_keys.issubset(wgs84_extent.keys()):
        west = float(wgs84_extent["west"])
        south = float(wgs84_extent["south"])
        east = float(wgs84_extent["east"])
        north = float(wgs84_extent["north"])
        if east <= west or north <= south:
            return None
        return {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        }
    pts = _extract_lonlat_pairs(wgs84_extent.get("coordinates"))
    if not pts:
        return None

    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    west = max(-180.0, min(180.0, min(lons)))
    east = max(-180.0, min(180.0, max(lons)))
    south = max(-90.0, min(90.0, min(lats)))
    north = max(-90.0, min(90.0, max(lats)))
    if east <= west or north <= south:
        return None
    return {
        "west": west,
        "south": south,
        "east": east,
        "north": north,
    }


def _region_from_bbox(bbox_wgs84: dict | None) -> list[float] | None:
    bbox = _bbox_from_wgs84_extent(bbox_wgs84)
    if not bbox:
        return None
    return [
        math.radians(bbox["west"]),
        math.radians(bbox["south"]),
        math.radians(bbox["east"]),
        math.radians(bbox["north"]),
        0.0,
        1000.0,
    ]


def _bbox_from_georef(georef: dict | None) -> dict | None:
    if not isinstance(georef, dict):
        return None
    maybe_bbox = georef.get("bbox_wgs84")
    if isinstance(maybe_bbox, dict):
        return maybe_bbox
    return None


def convert_to_cog(src_path: str, out_path: str | None = None) -> str:
    """
    Convert GeoTIFF -> COG using GDAL.
    """
    src = Path(src_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Raster source does not exist: {src}")

    if out_path is None:
        out_path = str(src.with_name(f"{src.stem}.cog.tif"))
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    gdal_translate = _which("gdal_translate")
    if not gdal_translate:
        raise RuntimeError(
            "gdal_translate is required for production COG generation but was not found in PATH."
        )

    _run(
        [
            gdal_translate,
            "-of",
            "COG",
            "-co",
            "COMPRESS=DEFLATE",
            "-co",
            "BLOCKSIZE=512",
            str(src),
            str(out),
        ]
    )
    return str(out)


def generate_xyz_tiles(
    src_cog_path: str,
    out_dir: str | None = None,
    min_zoom: int = 14,
    max_zoom: int = 22,
) -> str | None:
    """
    Generate XYZ tiles for mobile/offline workflows.
    """
    src = Path(src_cog_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"COG source not found for XYZ tiling: {src}")

    if out_dir is None:
        out_dir = str(src.with_suffix(""))
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    gdal2tiles = _which("gdal2tiles.py") or _which("gdal2tiles")
    if not gdal2tiles:
        raise RuntimeError(
            "gdal2tiles is required for xyz_tiles output but was not found in PATH."
        )

    _run(
        [
            gdal2tiles,
            "-z",
            f"{min_zoom}-{max_zoom}",
            str(src),
            str(out),
        ]
    )
    return str(out)


def convert_mesh_to_gltf(mesh_path: str, out_dir: str | None = None) -> str:
    """
    Convert mesh (OBJ/PLY/...) -> glTF/GLB when possible.
    """
    src = Path(mesh_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Mesh source does not exist: {src}")

    if src.suffix.lower() in {".glb", ".gltf"}:
        return str(src)

    target_dir = Path(out_dir or src.parent).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    glb = target_dir / f"{src.stem}.glb"

    obj2gltf = _which("obj2gltf")
    if obj2gltf and src.suffix.lower() == ".obj":
        _run([obj2gltf, "-i", str(src), "-o", str(glb)])
        return str(glb)

    assimp = _which("assimp")
    if assimp:
        _run([assimp, "export", str(src), str(glb)])
        return str(glb)

    raise RuntimeError(
        "No mesh->glTF converter available. Install obj2gltf or assimp, or provide GLB directly."
    )


def _write_single_tile_tileset(
    glb_path: Path,
    out_dir: Path,
    *,
    georef: dict | None = None,
    bbox_wgs84: dict | None = None,
) -> str:
    """
    Minimal self-hosted 3D Tiles representation using a single GLB content URI.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    dst_glb = out_dir / glb_path.name
    if glb_path.resolve() != dst_glb.resolve():
        shutil.copy2(glb_path, dst_glb)

    effective_bbox = _bbox_from_georef(georef) or bbox_wgs84
    region = _region_from_bbox(effective_bbox)
    if region is None:
        # Localized safe fallback only when georeferencing bounds are unavailable.
        region = [
            -0.01,
            -0.01,
            0.01,
            0.01,
            0.0,
            150.0,
        ]
    tileset = {
        "asset": {"version": "1.1"},
        "geometricError": 500,
        "root": {
            "boundingVolume": {
                "region": region
            },
            "geometricError": 0,
            "refine": "ADD",
            "content": {"uri": dst_glb.name},
        },
    }
    tileset_path = out_dir / "tileset.json"
    tileset_path.write_text(json.dumps(tileset, indent=2), encoding="utf-8")
    return str(out_dir)


def convert_mesh_to_3dtiles(
    mesh_path: str,
    out_dir: str | None = None,
    *,
    georef: dict | None = None,
    bbox_wgs84: dict | None = None,
) -> str:
    """
    Convert mesh output to web-streamable 3D Tiles.

    Strategy:
    - `PHOTOGRAMMETRY_3DTILES_CMD` must be set.
      command template receives `{input_gltf}` and `{output_dir}`.
    """
    gltf_or_glb = Path(convert_mesh_to_gltf(mesh_path)).resolve()
    target_dir = Path(
        out_dir or gltf_or_glb.parent / f"{gltf_or_glb.stem}.3dtiles"
    ).resolve()

    cmd_template = os.getenv("PHOTOGRAMMETRY_3DTILES_CMD", "").strip()
    if not cmd_template:
        allow_minimal = os.getenv("PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET", "0").lower() in {
            "1",
            "true",
            "yes",
        }
        if allow_minimal:
            return _write_single_tile_tileset(
                gltf_or_glb,
                target_dir,
                georef=georef,
                bbox_wgs84=bbox_wgs84,
            )
        raise RuntimeError(
            "PHOTOGRAMMETRY_3DTILES_CMD is required for production 3D Tiles conversion."
        )

    command = cmd_template.format(input_gltf=str(gltf_or_glb), output_dir=str(target_dir))
    subprocess.run(command, shell=True, check=True)
    return str(target_dir)


def inspect_raster_georeferencing(src_path: str) -> dict:
    """
    Lightweight georeferencing validation metadata for raster outputs.
    """
    src = Path(src_path).resolve()
    result = {
        "validated": False,
        "epsg": None,
        "has_geotransform": False,
        "bbox_wgs84": None,
        "size_px": None,
    }
    if not src.exists():
        result["error"] = "source_not_found"
        return result

    gdalinfo = _which("gdalinfo")
    if not gdalinfo:
        result["error"] = "gdalinfo_unavailable"
        return result

    try:
        proc = subprocess.run(
            [gdalinfo, "-json", str(src)],
            check=True,
            text=True,
            capture_output=True,
        )
        info = json.loads(proc.stdout)
    except Exception as exc:
        result["error"] = f"gdalinfo_failed:{exc}"
        return result

    size = info.get("size")
    if isinstance(size, list) and len(size) == 2:
        result["size_px"] = {"width": size[0], "height": size[1]}

    geo_transform = info.get("geoTransform")
    if isinstance(geo_transform, list) and len(geo_transform) >= 6:
        result["has_geotransform"] = True

    wkt = (info.get("coordinateSystem") or {}).get("wkt", "")
    if isinstance(wkt, str) and wkt:
        m = re.search(r'EPSG["\',\s]+(\d+)', wkt)
        if m:
            result["epsg"] = int(m.group(1))

    wgs84_extent = info.get("wgs84Extent")
    if isinstance(wgs84_extent, dict):
        result["bbox_wgs84"] = wgs84_extent

    result["validated"] = bool(result["has_geotransform"])
    return result
