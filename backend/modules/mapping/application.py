from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.fields.models import Field
from backend.modules.identity.models import User
from backend.modules.mapping.models import Asset, MappingJob
from backend.modules.mapping.repository import MappingRepository
from backend.modules.mapping.service.field_derivation import ring_to_polygon_wkt
from backend.modules.organizations.service import get_default_project


class MappingApplication:
    def __init__(self, repository: MappingRepository | None = None) -> None:
        self.repository = repository or MappingRepository()

    async def get_field(self, db: AsyncSession, *, field_id: int, user: User) -> Field | None:
        return await self.repository.get_owned_field(db, field_id=field_id, user=user)

    async def get_job(self, db: AsyncSession, *, job_id: int, user: User) -> MappingJob | None:
        return await self.repository.get_owned_job(db, job_id=job_id, user=user)

    async def get_asset(
        self, db: AsyncSession, *, asset_id: int, user: User
    ) -> tuple[Asset, int] | None:
        return await self.repository.get_owned_asset(db, asset_id=asset_id, user=user)

    async def get_asset_record(
        self, db: AsyncSession, *, asset_id: int
    ) -> tuple[Asset, int, int | None] | None:
        return await self.repository.get_asset_record(db, asset_id=asset_id)

    async def assets_for_model(self, db: AsyncSession, *, model_id: int) -> list[Asset]:
        return await self.repository.assets_for_model(db, model_id=model_id)

    async def latest_source_dir(self, db: AsyncSession) -> str | None:
        return await self.repository.latest_source_dir(db)

    async def list_versions(self, db: AsyncSession, *, field_id: int):
        return await self.repository.list_versions(db, field_id=field_id)

    async def create_derived_field(
        self, db: AsyncSession, *, user: User, name: str, ring: list[list[float]]
    ) -> Field | None:
        project = await get_default_project(db, org_id=int(user.org_id)) if user.org_id else None
        return await self.repository.create_field_from_wkt(
            db,
            user=user,
            project_id=project.id if project else None,
            name=name,
            polygon_wkt=ring_to_polygon_wkt(ring),
        )

    async def create_job(
        self,
        db: AsyncSession,
        *,
        field: Field,
        processor: str,
        params: dict,
        status: str = "pending",
    ) -> tuple[int, MappingJob]:
        model, job = await self.repository.create_job(
            db, field=field, processor=processor, params=params, status=status
        )
        await db.commit()
        await db.refresh(job)
        return model.id, job

    async def create_uncommitted_job(
        self, db: AsyncSession, *, field: Field, processor: str, status: str
    ) -> tuple[int, MappingJob]:
        model, job = await self.repository.create_job(
            db, field=field, processor=processor, params={}, status=status
        )
        return model.id, job

    async def save_upload_params(self, db: AsyncSession, *, job: MappingJob, params: dict) -> None:
        job.params = params
        await db.commit()
        await db.refresh(job)

    async def mark_enqueued(self, db: AsyncSession, *, job: MappingJob, task_id: str) -> None:
        job.status, job.progress, job.error, job.processor_task_id = "pending", 0, None, task_id
        await db.commit()

    async def mark_enqueue_failed(self, db: AsyncSession, *, job: MappingJob, error: str) -> None:
        job.status, job.error = "failed", error
        await db.commit()

    async def refresh(self, db: AsyncSession, *, job: MappingJob) -> None:
        await db.refresh(job)

    async def list_jobs_with_assets(
        self, db: AsyncSession, *, user: User, limit: int
    ) -> list[tuple[MappingJob, list[Asset]]]:
        jobs = await self.repository.list_owned_jobs(db, user=user, limit=limit)
        assets = await self.repository.assets_for_models(
            db, model_ids=sorted({int(job.model_id) for job in jobs})
        )
        by_model: dict[int, list[Asset]] = {}
        for asset in assets:
            by_model.setdefault(int(asset.model_id), []).append(asset)
        return [(job, by_model.get(int(job.model_id), [])) for job in jobs]

    async def latest_ready(
        self, db: AsyncSession, *, field_id: int
    ) -> tuple[MappingJob, list[Asset]] | None:
        latest = await self.repository.latest_ready(db, field_id=field_id)
        if latest is None:
            return None
        job, model_id = latest
        return job, await self.repository.assets_for_model(db, model_id=model_id)

    async def append_uploads(
        self, db: AsyncSession, *, job: MappingJob, uploaded_paths: list[str]
    ) -> int:
        params = dict(job.params) if isinstance(job.params, dict) else {}
        existing = params.get("uploaded_images")
        paths = list(existing) if isinstance(existing, list) else []
        paths.extend(uploaded_paths)
        params["uploaded_images"], params["uploaded_count"] = paths, len(paths)
        job.params = params
        job.status = "uploading" if paths else job.status
        await db.commit()
        return len(paths)

    async def delete_job(self, db: AsyncSession, *, job: MappingJob) -> None:
        await self.repository.delete_job(db, job=job)
        await db.commit()

    async def rollback(self, db: AsyncSession) -> None:
        await db.rollback()


mapping_application = MappingApplication()
