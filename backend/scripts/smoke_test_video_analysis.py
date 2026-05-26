"""Local smoke test for the offline video analysis pipeline.

Run from the repository root:
    python backend/scripts/smoke_test_video_analysis.py /path/to/video.mp4
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.database.session import Session  # noqa: E402
from backend.modules.video_analysis.repository import VideoAnalysisRepository  # noqa: E402
from backend.modules.video_analysis.service.pipeline import (  # noqa: E402
    OfflineVideoAnalysisPipeline,
)


async def run(video_path: str) -> None:
    async with Session() as db:
        repo = VideoAnalysisRepository(db)
        video = await repo.create_video(
            original_filename=Path(video_path).name,
            storage_path=video_path,
            content_type="video/mp4",
        )
        job = await repo.create_job(
            video=video,
            model_name="yolo26s.pt",
            frame_stride_seconds=1.0,
            confidence_threshold=0.35,
        )
        await OfflineVideoAnalysisPipeline(db).run(job.id)
        print(f"completed job_id={job.id}")


def main(video_path: str) -> None:
    asyncio.run(run(video_path))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python backend/scripts/smoke_test_video_analysis.py /path/to/video.mp4"
        )
    main(sys.argv[1])
