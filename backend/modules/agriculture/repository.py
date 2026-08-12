from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.models import (
    AgricultureAnalysisRun,
    AgricultureAnalysisLayer,
    AgricultureAnalysisStage,
    AgricultureObservation,
    AgricultureFieldProfile,
    AgricultureFlight,
    AgricultureTelemetrySample,
)
from backend.modules.agriculture.temporal_models import AgricultureFlightAlignment, AgricultureObservationChange, AgricultureObservationAnnotation, AgricultureObservationFeedback, AgricultureReviewAudit
class AgricultureRepository:
    async def get_profile(self, db: AsyncSession, *, field_id: int, user) -> AgricultureFieldProfile | None:
        result = await db.execute(
            select(AgricultureFieldProfile)
            .where(AgricultureFieldProfile.field_id == field_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        if user.org_id is not None and profile.org_id not in {None, user.org_id}:
            return None
        if user.org_id is None and profile.org_id is not None:
            return None
        return profile

    async def get_flight(self, db: AsyncSession, *, flight_id: str, user=None) -> AgricultureFlight | None:
        result = await db.execute(select(AgricultureFlight).where(AgricultureFlight.id == flight_id))
        flight = result.scalar_one_or_none()
        if flight is None or user is None:
            return flight
        if user.org_id is not None:
            return flight if flight.org_id == user.org_id else None
        return flight if flight.org_id is None else None

    async def get_flight_by_mission(self, db: AsyncSession, *, mission_id: str) -> AgricultureFlight | None:
        return await db.scalar(select(AgricultureFlight).where(AgricultureFlight.mission_id == mission_id))

    async def list_flights(self, db: AsyncSession, *, field_id: int, user, limit: int = 50) -> list[AgricultureFlight]:
        stmt = select(AgricultureFlight).where(AgricultureFlight.field_id == field_id)
        if user.org_id is not None:
            stmt = stmt.where(AgricultureFlight.org_id == user.org_id)
        else:
            stmt = stmt.where(AgricultureFlight.org_id.is_(None))
        stmt = stmt.order_by(AgricultureFlight.created_at.desc()).limit(max(1, min(limit, 200)))
        return list((await db.scalars(stmt)).all())

    async def list_telemetry(self, db: AsyncSession, *, flight_id: str) -> list[AgricultureTelemetrySample]:
        stmt = select(AgricultureTelemetrySample).where(
            AgricultureTelemetrySample.flight_id == flight_id
        ).order_by(AgricultureTelemetrySample.timestamp_utc.asc())
        return list((await db.scalars(stmt)).all())

    async def get_run_by_key(self, db: AsyncSession, *, flight_id: str, key: str) -> AgricultureAnalysisRun | None:
        return await db.scalar(select(AgricultureAnalysisRun).where(
            AgricultureAnalysisRun.flight_id == flight_id,
            AgricultureAnalysisRun.idempotency_key == key,
        ))

    async def list_runs(self, db: AsyncSession, *, flight_id: str, user, limit: int = 20) -> list[AgricultureAnalysisRun]:
        flight = await self.get_flight(db, flight_id=flight_id, user=user)
        if flight is None:
            return []
        stmt = select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.flight_id == flight_id).order_by(AgricultureAnalysisRun.created_at.desc()).limit(max(1, min(limit, 100)))
        return list((await db.scalars(stmt)).all())

    async def get_run(self, db: AsyncSession, *, run_id: str, user) -> AgricultureAnalysisRun | None:
        result = await db.execute(
            select(AgricultureAnalysisRun)
            .join(AgricultureFlight, AgricultureFlight.id == AgricultureAnalysisRun.flight_id)
            .where(AgricultureAnalysisRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return None
        flight = await self.get_flight(db, flight_id=run.flight_id, user=user)
        return run if flight is not None else None

    async def get_observation(self, db: AsyncSession, *, observation_id: str, user) -> AgricultureObservation | None:
        observation = await db.get(AgricultureObservation, observation_id)
        if observation is None:
            return None
        flight = await self.get_flight(db, flight_id=observation.flight_id, user=user)
        return observation if flight is not None else None

    async def list_observations(self, db: AsyncSession, *, run_id: str, user, observation_type: str | None = None, min_severity: float | None = None, min_confidence: float | None = None, trend: str | None = None, detected_from: datetime | None = None, detected_to: datetime | None = None, bbox: tuple[float, float, float, float] | None = None, limit: int = 200, offset: int = 0) -> tuple[list[AgricultureObservation], int]:
        stmt = select(AgricultureObservation).where(AgricultureObservation.run_id == run_id)
        if observation_type: stmt = stmt.where(AgricultureObservation.observation_type == observation_type)
        if min_severity is not None: stmt = stmt.where(AgricultureObservation.severity >= min_severity)
        if min_confidence is not None: stmt = stmt.where(AgricultureObservation.confidence >= min_confidence)
        if trend: stmt = stmt.where(AgricultureObservation.trend == trend)
        if detected_from: stmt = stmt.where(AgricultureObservation.last_detected >= detected_from)
        if detected_to: stmt = stmt.where(AgricultureObservation.first_detected <= detected_to)
        if bbox:
            stmt = stmt.where(func.ST_Intersects(
                AgricultureObservation.geometry,
                func.ST_MakeEnvelope(*bbox, 4326),
            ))
        visible = await self.get_run(db, run_id=run_id, user=user)
        if visible is None: return [], 0
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(await db.scalar(count_stmt) or 0)
        stmt = stmt.order_by(AgricultureObservation.severity.desc(), AgricultureObservation.id.asc()).offset(max(0, offset)).limit(max(1, min(limit, 500)))
        return list((await db.scalars(stmt)).all()), total

    async def list_spatial_observations(self, db: AsyncSession, *, run_id: str, user, bbox: tuple[float, float, float, float] | None, observation_type: str | None, min_severity: float, min_confidence: float, limit: int = 10000, offset: int = 0) -> tuple[list[AgricultureObservation], int]:
        """Filter and count in PostGIS before applying the response bound."""
        stmt = select(AgricultureObservation).join(
            AgricultureFlight,
            AgricultureFlight.id == AgricultureObservation.flight_id,
        ).where(
            AgricultureObservation.run_id == run_id,
            AgricultureObservation.severity >= min_severity,
            AgricultureObservation.confidence >= min_confidence,
        )
        if user.org_id is not None:
            stmt = stmt.where(AgricultureFlight.org_id == user.org_id)
        else:
            stmt = stmt.where(AgricultureFlight.org_id.is_(None))
        if observation_type:
            stmt = stmt.where(AgricultureObservation.observation_type == observation_type)
        if bbox:
            stmt = stmt.where(
                func.ST_Intersects(
                    AgricultureObservation.geometry,
                    func.ST_MakeEnvelope(*bbox, 4326),
                )
            )
        total = int(
            await db.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )
        result = await db.scalars(
            stmt.order_by(
                AgricultureObservation.severity.desc(),
                AgricultureObservation.id.asc(),
            ).offset(max(0, offset)).limit(max(1, min(limit, 10000)))
        )
        return list(result.all()), total

    async def get_layer(self, db: AsyncSession, *, run_id: str, layer_name: str, user) -> AgricultureAnalysisLayer | None:
        run = await self.get_run(db, run_id=run_id, user=user)
        if run is None: return None
        return await db.scalar(select(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == run_id, AgricultureAnalysisLayer.layer_name == layer_name))

    async def list_stages(self, db: AsyncSession, *, run_id: str) -> list[AgricultureAnalysisStage]:
        stmt = select(AgricultureAnalysisStage).where(AgricultureAnalysisStage.run_id == run_id).order_by(AgricultureAnalysisStage.created_at.asc())
        return list((await db.scalars(stmt)).all())

    async def get_alignment(self, db: AsyncSession, *, current_flight_id: str, reference_flight_id: str) -> AgricultureFlightAlignment | None:
        return await db.scalar(select(AgricultureFlightAlignment).where(AgricultureFlightAlignment.current_flight_id == current_flight_id, AgricultureFlightAlignment.reference_flight_id == reference_flight_id))

    async def list_changes(self, db: AsyncSession, *, current_flight_id: str, user, limit: int = 2000) -> list[AgricultureObservationChange]:
        flight = await self.get_flight(db, flight_id=current_flight_id, user=user)
        if flight is None: return []
        stmt = select(AgricultureObservationChange).where(AgricultureObservationChange.current_flight_id == current_flight_id).order_by(AgricultureObservationChange.confidence.desc(), AgricultureObservationChange.id.asc()).limit(max(1, min(limit, 5000)))
        return list((await db.scalars(stmt)).all())

    async def list_audits(self, db: AsyncSession, *, observation_id: str, user) -> list[AgricultureReviewAudit]:
        observation = await self.get_observation(db, observation_id=observation_id, user=user)
        if observation is None: return []
        return list((await db.scalars(select(AgricultureReviewAudit).where(AgricultureReviewAudit.observation_id == observation_id).order_by(AgricultureReviewAudit.created_at.asc()))).all())

    async def list_annotations(self, db: AsyncSession, *, observation_id: str, user) -> list[AgricultureObservationAnnotation]:
        observation = await self.get_observation(db, observation_id=observation_id, user=user)
        if observation is None: return []
        return list((await db.scalars(select(AgricultureObservationAnnotation).where(AgricultureObservationAnnotation.observation_id == observation_id).order_by(AgricultureObservationAnnotation.version.desc()))).all())

    async def list_feedback(self, db: AsyncSession, *, observation_id: str, user) -> list[AgricultureObservationFeedback]:
        observation = await self.get_observation(db, observation_id=observation_id, user=user)
        if observation is None:
            return []
        return list((await db.scalars(select(AgricultureObservationFeedback).where(AgricultureObservationFeedback.observation_id == observation_id).order_by(AgricultureObservationFeedback.created_at.desc()))).all())


agriculture_repository = AgricultureRepository()
