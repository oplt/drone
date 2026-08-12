#!/usr/bin/env python3
"""CLEAN-001 read-only inventory for instance_segmentation remnants.

Counts Vision projects with task_type=instance_segmentation and annotations
(images) with non-null segmentation JSON. Does not mutate data.

Usage:
  python backend/scripts/inventory_instance_segmentation.py
  python backend/scripts/inventory_instance_segmentation.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import func, select


async def run_inventory() -> dict[str, Any]:
    from backend.core.database.session import Session
    from backend.modules.vision_models.dataset_models import (
        Annotation,
        DatasetImage,
        VisionProject,
    )

    async with Session() as session:
        project_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(VisionProject)
                    .where(VisionProject.task_type == "instance_segmentation")
                )
            ).scalar_one()
        )
        annotation_with_segmentation = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Annotation)
                    .where(Annotation.segmentation.is_not(None))
                )
            ).scalar_one()
        )
        images_with_segmentation = int(
            (
                await session.execute(
                    select(func.count(func.distinct(Annotation.image_id)))
                    .select_from(Annotation)
                    .where(Annotation.segmentation.is_not(None))
                )
            ).scalar_one()
        )
        # Touch DatasetImage so the inventory proves the join path is valid.
        image_total = int(
            (await session.execute(select(func.count()).select_from(DatasetImage))).scalar_one()
        )

    safe_to_drop_schema = (
        project_count == 0
        and annotation_with_segmentation == 0
        and images_with_segmentation == 0
    )
    return {
        "read_only": True,
        "projects_instance_segmentation": project_count,
        "annotations_with_segmentation": annotation_with_segmentation,
        "images_with_non_null_segmentation": images_with_segmentation,
        "dataset_images_total": image_total,
        "safe_to_drop_schema_remnants": safe_to_drop_schema,
        "recommendation": (
            "Schema/check-constraint removal is allowed only after this inventory "
            "reports zero rows in every tenant environment and a reviewed migration "
            "is approved."
            if not safe_to_drop_schema
            else (
                "Inventory is empty in this database; a conditional destructive "
                "migration may be drafted, but do not ship drops without repeating "
                "this scan on production."
            )
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON only.",
    )
    args = parser.parse_args()
    try:
        report = asyncio.run(run_inventory())
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"inventory failed (read-only): {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print("CLEAN-001 instance_segmentation inventory (read-only)")
        print(f"  projects task_type=instance_segmentation: {report['projects_instance_segmentation']}")
        print(f"  annotations with segmentation JSON:     {report['annotations_with_segmentation']}")
        print(f"  distinct images with segmentation:      {report['images_with_non_null_segmentation']}")
        print(f"  dataset images total:                   {report['dataset_images_total']}")
        print(f"  safe_to_drop_schema_remnants:           {report['safe_to_drop_schema_remnants']}")
        print(f"  recommendation: {report['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
