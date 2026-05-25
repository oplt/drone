from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.fields.models import Field
from backend.modules.identity.models import User
from backend.modules.mapping.models import Asset, FieldModel, MappingJob
from backend.modules.missions.flight_models import FlightEvent
from backend.modules.organizations.service import ownership_clause, user_can_access_resource


class MappingRepository:
    async def get_owned_field(self, db: AsyncSession, *, field_id: int, user: User) -> Field | None:
        return await db.scalar(
            select(Field)
            .where(Field.id == field_id)
            .where(ownership_clause(user=user, owner_col=Field.owner_id, org_col=Field.org_id))
        )

    async def get_owned_job(
        self, db: AsyncSession, *, job_id: int, user: User
    ) -> MappingJob | None:
        row = await db.execute(
            select(MappingJob, Field)
            .join(Field, MappingJob.field_id == Field.id)
            .where(MappingJob.id == job_id)
            .where(ownership_clause(user=user, owner_col=Field.owner_id, org_col=Field.org_id))
        )
        pair = row.first()
        return pair[0] if pair else None

    async def get_owned_asset(
        self, db: AsyncSession, *, asset_id: int, user: User
    ) -> tuple[Asset, int] | None:
        row = await self.get_asset_record(db, asset_id=asset_id)
        if row is None:
            return None
        asset, owner_id, org_id = row
        if not user_can_access_resource(user, owner_id=owner_id, org_id=org_id):
            return None
        return asset, int(owner_id)

    async def get_asset_record(
        self, db: AsyncSession, *, asset_id: int
    ) -> tuple[Asset, int, int | None] | None:
        row = await db.execute(
            select(Asset, Field.owner_id, Field.org_id)
            .join(FieldModel, Asset.model_id == FieldModel.id)
            .join(Field, FieldModel.field_id == Field.id)
            .where(Asset.id == asset_id)
        )
        pair = row.first()
        if pair is None or pair[1] is None:
            return None
        return pair[0], int(pair[1]), pair[2]

    async def assets_for_model(self, db: AsyncSession, *, model_id: int) -> list[Asset]:
        rows = await db.execute(select(Asset).where(Asset.model_id == model_id).order_by(Asset.id))
        return list(rows.scalars().all())

    async def latest_source_dir(self, db: AsyncSession) -> str | None:
        data = await db.scalar(
            select(FlightEvent.data)
            .where(FlightEvent.type == "photogrammetry_mapping_job_params")
            .order_by(FlightEvent.id.desc())
            .limit(1)
        )
        if not isinstance(data, dict):
            return None
        drone_sync = data.get("drone_sync")
        source_dir = drone_sync.get("source_dir") if isinstance(drone_sync, dict) else None
        return source_dir.strip() if isinstance(source_dir, str) and source_dir.strip() else None

    async def create_field_from_wkt(
        self,
        db: AsyncSession,
        *,
        user: User,
        project_id: int | None,
        name: str,
        polygon_wkt: str,
    ) -> Field | None:
        result = await db.execute(
            text(
                """
                INSERT INTO fields (owner_id, org_id, project_id, name, boundary, area_ha, centroid)
                VALUES (:owner_id, :org_id, :project_id, :name,
                    ST_GeomFromText(:polygon_wkt, 4326),
                    ST_Area(ST_Transform(ST_GeomFromText(:polygon_wkt, 4326), 3857)) / 10000.0,
                    ST_Centroid(ST_GeomFromText(:polygon_wkt, 4326)))
                RETURNING id
                """
            ),
            {
                "owner_id": user.id,
                "org_id": user.org_id,
                "project_id": project_id,
                "name": name,
                "polygon_wkt": polygon_wkt,
            },
        )
        return await db.get(Field, int(result.scalar_one()))

    async def next_version(self, db: AsyncSession, *, field_id: int) -> int:
        version = await db.scalar(
            select(func.max(FieldModel.version)).where(FieldModel.field_id == field_id)
        )
        return int(version or 0) + 1

    async def create_job(
        self,
        db: AsyncSession,
        *,
        field: Field,
        processor: str,
        params: dict,
        status: str = "pending",
    ) -> tuple[FieldModel, MappingJob]:
        model = FieldModel(
            field_id=field.id,
            version=await self.next_version(db, field_id=field.id),
            status="pending",
        )
        db.add(model)
        await db.flush()
        job = MappingJob(
            field_id=field.id,
            model_id=model.id,
            status=status,
            progress=0,
            processor=processor,
            org_id=field.org_id,
            project_id=field.project_id,
            params=params,
        )
        db.add(job)
        await db.flush()
        return model, job

    async def list_owned_jobs(
        self, db: AsyncSession, *, user: User, limit: int
    ) -> list[MappingJob]:
        rows = await db.execute(
            select(MappingJob)
            .join(Field, MappingJob.field_id == Field.id)
            .where(ownership_clause(user=user, owner_col=Field.owner_id, org_col=Field.org_id))
            .order_by(MappingJob.id.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())

    async def assets_for_models(self, db: AsyncSession, *, model_ids: list[int]) -> list[Asset]:
        if not model_ids:
            return []
        rows = await db.execute(
            select(Asset).where(Asset.model_id.in_(model_ids)).order_by(Asset.model_id, Asset.id)
        )
        return list(rows.scalars().all())

    async def latest_ready(
        self, db: AsyncSession, *, field_id: int
    ) -> tuple[MappingJob, int] | None:
        model = await db.scalar(
            select(FieldModel)
            .where(FieldModel.field_id == field_id, FieldModel.status == "ready")
            .order_by(FieldModel.version.desc())
            .limit(1)
        )
        if model is None:
            return None
        job = await db.scalar(
            select(MappingJob)
            .where(MappingJob.model_id == model.id)
            .order_by(MappingJob.id.desc())
            .limit(1)
        )
        return (job, model.id) if job else None

    async def list_versions(self, db: AsyncSession, *, field_id: int) -> list[FieldModel]:
        rows = await db.execute(
            select(FieldModel)
            .where(FieldModel.field_id == field_id)
            .order_by(FieldModel.version.desc())
        )
        return list(rows.scalars().all())

    async def jobs_for_model_count(self, db: AsyncSession, *, model_id: int) -> int:
        return int(
            await db.scalar(
                select(func.count(MappingJob.id)).where(MappingJob.model_id == model_id)
            )
            or 0
        )

    async def delete_job(self, db: AsyncSession, *, job: MappingJob) -> None:
        if await self.jobs_for_model_count(db, model_id=job.model_id) <= 1:
            model = await db.get(FieldModel, job.model_id)
            await db.delete(model if model is not None else job)
        else:
            await db.delete(job)
