"""Authenticated model release and drift-governance endpoints.

Legacy Agriculture model-registry writes are intentionally read-only after
ADR-001. Lifecycle publish/deploy/archive happens through Vision Models and
capability releases.
"""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.temporal_models import (
    AgricultureModelQualityReport,
    AgricultureModelVersion,
)
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write

router = APIRouter(prefix="/agriculture", tags=["agriculture-model-governance"])


def _org_id(org_user: OrgUser) -> int | None:
    return getattr(org_user.user, "org_id", None)


def _legacy_registry_read_only() -> NoReturn:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "LEGACY_MODEL_REGISTRY_READ_ONLY",
            "message": "This legacy registry is available for migration review only. Use Vision Models for lifecycle operations.",
        },
    )


async def _owned_model(
    db: AsyncSession, model_version_id: str, org_user: OrgUser
) -> AgricultureModelVersion:
    model = await db.scalar(
        select(AgricultureModelVersion).where(
            AgricultureModelVersion.id == model_version_id,
            AgricultureModelVersion.org_id == _org_id(org_user),
        )
    )
    if model is None:
        raise HTTPException(status_code=404, detail="Agriculture model version not found")
    return model


@router.get("/models")
async def list_models(
    task: str | None = None,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[dict[str, Any]]:
    stmt = (
        select(AgricultureModelVersion)
        .where(AgricultureModelVersion.org_id == _org_id(org_user))
        .order_by(AgricultureModelVersion.created_at.desc())
    )
    if task:
        stmt = stmt.where(AgricultureModelVersion.task == task)
    rows = list((await db.scalars(stmt)).all())
    return [
        {
            "id": row.id,
            "task": row.task,
            "version": row.version,
            "status": row.status,
            "artifact_uri": row.artifact_uri,
            "dataset_key": row.dataset_key,
            "config": row.config,
            "metrics": row.metrics,
            "deployed_at": row.deployed_at,
            "created_at": row.created_at,
            "migration_state": getattr(row, "migration_state", None),
            "linked_capability_release_id": getattr(
                row, "linked_capability_release_id", None
            ),
        }
        for row in rows
    ]


@router.get("/models/{model_version_id}/quality-reports")
async def list_quality_reports(
    model_version_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[dict[str, Any]]:
    model = await _owned_model(db, model_version_id, org_user)
    rows = list(
        (
            await db.scalars(
                select(AgricultureModelQualityReport)
                .where(AgricultureModelQualityReport.model_version_id == model.id)
                .order_by(AgricultureModelQualityReport.created_at.desc())
            )
        ).all()
    )
    return [
        {
            "id": row.id,
            "model_version_id": row.model_version_id,
            "scope": row.scope,
            "metrics": row.metrics,
            "slices": row.slices,
            "drift": row.drift,
            "evaluation_checksum": row.evaluation_checksum,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/models/{model_version_id}/release-gate")
async def model_release_gate(
    model_version_id: str,
    crop_type: str | None = None,
    growth_stage: str | None = None,
    sensor_type: str = "rgb",
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    _ = (model_version_id, crop_type, growth_stage, sensor_type, db, org_user)
    _legacy_registry_read_only()


class ShadowEvaluationIn(BaseModel):
    metrics: dict[str, float] = Field(default_factory=dict)
    crop_type: str | None = None
    growth_stage: str | None = None
    sensor_type: str | None = None
    incumbent_metrics: dict[str, float] = Field(default_factory=dict)
    threshold_overrides: dict[str, float] = Field(default_factory=dict)


class DriftMonitorIn(BaseModel):
    current: dict[str, float]
    baseline: dict[str, float]
    slices: dict[str, dict[str, float]] = Field(default_factory=dict)
    warning_delta: float = Field(default=0.20, ge=0, le=1)
    retrain_delta: float = Field(default=0.35, ge=0, le=1)


@router.post("/models/{model_version_id}/shadow-evaluation")
async def shadow_evaluation(
    model_version_id: str,
    payload: ShadowEvaluationIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> dict[str, Any]:
    _ = (model_version_id, payload, db, org_user)
    _legacy_registry_read_only()


@router.post("/models/{model_version_id}/publish")
async def publish_model(
    model_version_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> dict[str, Any]:
    _ = (model_version_id, db, org_user)
    _legacy_registry_read_only()


@router.post("/models/{model_version_id}/rollback/{target_model_version_id}")
async def rollback_model(
    model_version_id: str,
    target_model_version_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> dict[str, Any]:
    _ = (model_version_id, target_model_version_id, db, org_user)
    _legacy_registry_read_only()


@router.post("/models/{model_version_id}/drift-monitor")
async def monitor_model_drift(
    model_version_id: str,
    payload: DriftMonitorIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> dict[str, Any]:
    _ = (model_version_id, payload, db, org_user)
    _legacy_registry_read_only()
