import asyncio
from backend.ml.patrol.pipeline import DroneAnomalyPipeline


async def main():
    pipeline = DroneAnomalyPipeline()
    await pipeline.run_forever()


if __name__ == "__main__":
    asyncio.run(main())