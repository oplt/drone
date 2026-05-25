from __future__ import annotations

from collections.abc import Awaitable, Callable


class MappingProcessingJob:
    def __init__(
        self,
        pipeline,
        before_run: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.before_run = before_run

    async def run(self, *, job_id: int, progress_cb: Callable[[dict], None] | None = None) -> dict:
        if self.before_run is not None:
            await self.before_run()
        return await self.pipeline.process_job(job_id=job_id, progress_cb=progress_cb)
