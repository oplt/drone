from __future__ import annotations

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


class OutputsMixin:
    """Output discovery and mock artifact resolution."""

    @staticmethod
    def _extract_archive(*, archive_path: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.infolist():
                target = (destination / member.filename).resolve()
                if not str(target).startswith(str(destination.resolve())):
                    raise RuntimeError(f"Unsafe archive path detected: {member.filename}")
            zf.extractall(destination)

    @staticmethod
    def _first_match(root: Path, patterns: list[str]) -> Path | None:
        for pattern in patterns:
            for item in root.glob(pattern):
                if item.exists() and item.is_file():
                    return item.resolve()
        return None

    def _locate_outputs(self, extracted_root: Path) -> dict[str, str]:
        ortho = self._first_match(
            extracted_root,
            [
                "**/odm_orthophoto/odm_orthophoto.tif",
                "**/*orthophoto*.tif",
                "**/*orthomosaic*.tif",
            ],
        )
        dsm = self._first_match(
            extracted_root,
            [
                "**/odm_dem/dsm.tif",
                "**/*dsm*.tif",
            ],
        )
        dtm = self._first_match(
            extracted_root,
            [
                "**/odm_dem/dtm.tif",
                "**/*dtm*.tif",
            ],
        )
        mesh = self._first_match(
            extracted_root,
            [
                "**/odm_texturing/*textured*.glb",
                "**/odm_texturing/*textured*.obj",
                "**/*mesh*.glb",
                "**/*mesh*.obj",
            ],
        )
        point_cloud = self._first_match(
            extracted_root,
            [
                "**/*.laz",
                "**/*.las",
            ],
        )

        if not ortho or not dsm or not mesh:
            raise RuntimeError(
                "WebODM export is missing required artifacts (orthophoto, dsm, mesh). "
                f"Located: orthophoto={bool(ortho)}, dsm={bool(dsm)}, mesh={bool(mesh)}"
            )

        outputs: dict[str, str] = {
            "orthophoto": str(ortho),
            "dsm": str(dsm),
            "mesh": str(mesh),
        }
        if dtm:
            outputs["dtm"] = str(dtm)
        if point_cloud:
            outputs["point_cloud"] = str(point_cloud)
        logger.info(
            "WebODM outputs located: root=%s keys=%s",
            extracted_root,
            sorted(outputs.keys()),
        )
        return outputs

    def _mock_outputs(self) -> dict[str, str]:
        ortho = self.mock_outputs_dir / "orthophoto.tif"
        dsm = self.mock_outputs_dir / "dsm.tif"
        dtm = self.mock_outputs_dir / "dtm.tif"
        mesh_obj = self.mock_outputs_dir / "mesh.obj"
        mesh_glb = self.mock_outputs_dir / "mesh.glb"
        mesh = mesh_glb if mesh_glb.exists() else mesh_obj
        point_cloud_laz = self.mock_outputs_dir / "point_cloud.laz"
        point_cloud_las = self.mock_outputs_dir / "point_cloud.las"
        point_cloud = (
            point_cloud_laz
            if point_cloud_laz.exists()
            else point_cloud_las
            if point_cloud_las.exists()
            else None
        )

        if not ortho.exists():
            raise FileNotFoundError(f"Mock orthophoto not found: {ortho}")
        if not dsm.exists():
            raise FileNotFoundError(f"Mock DSM not found: {dsm}")
        if not mesh.exists():
            raise FileNotFoundError(
                f"Mock mesh not found (expected mesh.glb or mesh.obj in {self.mock_outputs_dir})"
            )

        outputs: dict[str, str] = {
            "orthophoto": str(ortho),
            "dsm": str(dsm),
            "mesh": str(mesh),
        }
        if dtm.exists():
            outputs["dtm"] = str(dtm)
        if point_cloud is not None:
            outputs["point_cloud"] = str(point_cloud)
        logger.info(
            "WebODM mock outputs resolved: root=%s keys=%s",
            self.mock_outputs_dir,
            sorted(outputs.keys()),
        )
        return outputs

