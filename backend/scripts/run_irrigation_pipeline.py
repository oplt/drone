from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.irrigation.service.processing import irrigation_service
from backend.modules.missions.runtime_models import MissionRuntime


async def _run(mission_id: str, force: bool) -> None:
    async with Session() as db:
        mission = await db.scalar(
            select(MissionRuntime).where(MissionRuntime.client_flight_id == mission_id)
        )
        if mission is None:
            raise SystemExit(f"Mission not found: {mission_id}")
        layer = await irrigation_service.process_mission(db, mission=mission, force=force)
        print(
            f"mission_id={mission_id} status={layer.status} captures={layer.capture_count} "
            f"preview={layer.stitched_image_uri}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run irrigation processing for one mission.")
    parser.add_argument("mission_id", help="Mission client_flight_id")
    parser.add_argument("--force", action="store_true", help="Rebuild even if already completed")
    args = parser.parse_args()
    asyncio.run(_run(args.mission_id, args.force))


if __name__ == "__main__":
    main()
