import asyncio
import logging

from backend.core.config.runtime import setup_logging
from backend.core.database.session import close_db, init_db
from backend.modules.vehicle_runtime.factory import build_orchestrator

logger = logging.getLogger(__name__)

# Backward-compatible alias for modules that still import from the CLI entrypoint.
_build_orchestrator = build_orchestrator


# Optional CLI entrypoint
async def main():
    setup_logging()
    await init_db()
    orch = await build_orchestrator()
    await orch.run("Jerrabomberra Grassland Nature Reserve", "Alexander Maconochie Centre", alt=35)
    await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program terminated safely")
