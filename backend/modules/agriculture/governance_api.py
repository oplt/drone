"""Authenticated model release and drift-governance endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.release_governance import drift_retraining_trigger, evaluate_shadow_release, resolve_thresholds, validate_rgb_release_evidence
from backend.modules.agriculture.temporal_models import AgricultureDatasetExport, AgricultureModelQualityReport, AgricultureModelVersion
from backend.modules.agriculture.p5_models import AgricultureGovernanceAudit
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write

router = APIRouter(prefix="/agriculture", tags=["agriculture-model-governance"])


def _org_id(org_user: OrgUser) -> int | None:
    return getattr(org_user.user, "org_id", None)


async def _owned_model(db: AsyncSession, model_version_id: str, org_user: OrgUser) -> AgricultureModelVersion:
    model = await db.scalar(select(AgricultureModelVersion).where(AgricultureModelVersion.id == model_version_id, AgricultureModelVersion.org_id == _org_id(org_user)))
    if model is None:
        raise HTTPException(status_code=404, detail="Agriculture model version not found")
    return model


@router.get("/models")
async def list_models(task: str | None = None, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)) -> list[dict[str, Any]]:
    stmt = select(AgricultureModelVersion).where(AgricultureModelVersion.org_id == _org_id(org_user)).order_by(AgricultureModelVersion.created_at.desc())
    if task:
        stmt = stmt.where(AgricultureModelVersion.task == task)
    rows = list((await db.scalars(stmt)).all())
    return [{"id": row.id, "task": row.task, "version": row.version, "status": row.status, "artifact_uri": row.artifact_uri, "dataset_key": row.dataset_key, "config": row.config, "metrics": row.metrics, "deployed_at": row.deployed_at, "created_at": row.created_at} for row in rows]


@router.get("/models/{model_version_id}/quality-reports")
async def list_quality_reports(model_version_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)) -> list[dict[str, Any]]:
    model = await _owned_model(db, model_version_id, org_user)
    rows = list((await db.scalars(select(AgricultureModelQualityReport).where(AgricultureModelQualityReport.model_version_id == model.id).order_by(AgricultureModelQualityReport.created_at.desc()))).all())
    return [{"id": row.id, "model_version_id": row.model_version_id, "scope": row.scope, "metrics": row.metrics, "slices": row.slices, "drift": row.drift, "evaluation_checksum": row.evaluation_checksum, "created_at": row.created_at} for row in rows]


@router.get("/models/{model_version_id}/release-gate")
async def model_release_gate(model_version_id: str, crop_type: str | None = None, growth_stage: str | None = None, sensor_type: str = "rgb", db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)) -> dict[str, Any]:
    model = await _owned_model(db, model_version_id, org_user)
    report = await db.scalar(select(AgricultureModelQualityReport).where(AgricultureModelQualityReport.model_version_id == model.id).order_by(AgricultureModelQualityReport.created_at.desc()).limit(1))
    dataset_row = await db.scalar(select(AgricultureDatasetExport).where(AgricultureDatasetExport.org_id == _org_id(org_user), AgricultureDatasetExport.dataset_key == model.dataset_key, AgricultureDatasetExport.status == "completed").order_by(AgricultureDatasetExport.created_at.desc())) if model.dataset_key else None
    evidence = validate_rgb_release_evidence(model={"artifact_uri": model.artifact_uri, "dataset_key": model.dataset_key, "config": model.config}, report={"metrics": report.metrics if report else {}}, dataset={"status": dataset_row.status, "manifest": dataset_row.manifest} if dataset_row else None, crop_type=crop_type, growth_stage=growth_stage, sensor_type=sensor_type)
    metric_gate = dict((report.drift or {}).get("thresholds", {}) if report else {})
    return {"model_id": model.id, "task": model.task, "version": model.version, "status": model.status, "report_id": report.id if report else None, "evaluation_checksum": report.evaluation_checksum if report else None, "metric_gate": metric_gate, "evidence_gate": evidence, "publishable": model.status in {"validated", "deployed"} and bool(report) and bool((report.drift or {}).get("publishable")) and evidence["publishable"]}


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
async def shadow_evaluation(model_version_id: str, payload: ShadowEvaluationIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)) -> dict[str, Any]:
    model = await _owned_model(db, model_version_id, org_user)
    if model.status in {"deployed", "retired"}:
        raise HTTPException(status_code=409, detail="Only candidate or validated models can enter shadow evaluation")
    thresholds = resolve_thresholds(crop=payload.crop_type, stage=payload.growth_stage, sensor=payload.sensor_type, overrides=payload.threshold_overrides)
    result = evaluate_shadow_release(candidate={"metrics": payload.metrics}, incumbent=payload.incumbent_metrics, thresholds=thresholds)
    dataset_row = await db.scalar(select(AgricultureDatasetExport).where(AgricultureDatasetExport.org_id == _org_id(org_user), AgricultureDatasetExport.dataset_key == model.dataset_key, AgricultureDatasetExport.status == "completed").order_by(AgricultureDatasetExport.created_at.desc())) if model.dataset_key else None
    evidence = validate_rgb_release_evidence(model={"artifact_uri": model.artifact_uri, "dataset_key": model.dataset_key, "config": model.config}, report={"metrics": payload.metrics}, dataset={"status": dataset_row.status, "manifest": dataset_row.manifest} if dataset_row else None, crop_type=payload.crop_type, growth_stage=payload.growth_stage, sensor_type=payload.sensor_type or "rgb")
    result = {**result, "publishable": bool(result["publishable"] and evidence["publishable"]), "status": "pass" if result["publishable"] and evidence["publishable"] else "blocked", "evidence_gate": evidence}
    report_blob = {"scope": "shadow", "metrics": payload.metrics, "slices": {"crop_type": payload.crop_type, "growth_stage": payload.growth_stage, "sensor_type": payload.sensor_type}, "drift": result}
    report = AgricultureModelQualityReport(model_version_id=model.id, evaluation_checksum=hashlib.sha256(json.dumps(report_blob, sort_keys=True).encode()).hexdigest(), **report_blob)
    db.add(report)
    if result["publishable"]:
        model.status = "validated"
    db.add(AgricultureGovernanceAudit(org_id=model.org_id, entity_type="model", entity_id=model.id, actor_user_id=org_user.user.id, action="shadow_evaluation", from_status="candidate", to_status=model.status, reason="Evidence-backed shadow evaluation", payload={"report_id": report.id, "publishable": result["publishable"]}))
    await db.commit()
    return {"model_version_id": model.id, "model_status": model.status, "report_id": report.id, **result}


@router.post("/models/{model_version_id}/publish")
async def publish_model(model_version_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)) -> dict[str, Any]:
    model = await _owned_model(db, model_version_id, org_user)
    if model.status != "validated":
        raise HTTPException(status_code=409, detail="Model requires a passing shadow evaluation before publish")
    deployed = list((await db.scalars(select(AgricultureModelVersion).where(AgricultureModelVersion.org_id == model.org_id, AgricultureModelVersion.task == model.task, AgricultureModelVersion.status == "deployed"))).all())
    for previous in deployed:
        previous.status = "retired"
    model.status = "deployed"
    model.deployed_at = datetime.now(UTC)
    db.add(AgricultureGovernanceAudit(org_id=model.org_id, entity_type="model", entity_id=model.id, actor_user_id=org_user.user.id, action="publish", from_status="validated", to_status="deployed", reason="Evidence-backed model publish", payload={"replaced": [row.id for row in deployed]}))
    await db.commit()
    return {"id": model.id, "task": model.task, "version": model.version, "status": model.status, "replaced": [row.id for row in deployed]}


@router.post("/models/{model_version_id}/rollback/{target_model_version_id}")
async def rollback_model(model_version_id: str, target_model_version_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)) -> dict[str, Any]:
    source = await _owned_model(db, model_version_id, org_user)
    target = await _owned_model(db, target_model_version_id, org_user)
    if source.task != target.task:
        raise HTTPException(status_code=404, detail="Compatible agriculture model versions not found")
    deployed = list((await db.scalars(select(AgricultureModelVersion).where(AgricultureModelVersion.org_id == source.org_id, AgricultureModelVersion.task == source.task, AgricultureModelVersion.status == "deployed"))).all())
    for row in deployed:
        row.status = "retired"
    target.status = "deployed"
    target.deployed_at = datetime.now(UTC)
    db.add(AgricultureGovernanceAudit(org_id=source.org_id, entity_type="model", entity_id=target.id, actor_user_id=org_user.user.id, action="rollback", from_status=source.status, to_status="deployed", reason="Model rollback", payload={"rolled_back_from": source.id, "deployed_model_id": target.id}))
    await db.commit()
    return {"rolled_back_from": source.id, "deployed_model_id": target.id, "status": target.status}


@router.post("/models/{model_version_id}/drift-monitor")
async def monitor_model_drift(model_version_id: str, payload: DriftMonitorIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)) -> dict[str, Any]:
    model = await _owned_model(db, model_version_id, org_user)
    result = drift_retraining_trigger(current=payload.current, baseline=payload.baseline, slices=payload.slices, warning_delta=payload.warning_delta, retrain_delta=payload.retrain_delta)
    model.config = {**(model.config or {}), "last_drift_monitor": result, "retraining_required": result["retraining_triggered"]}
    db.add(AgricultureGovernanceAudit(org_id=model.org_id, entity_type="model", entity_id=model.id, actor_user_id=org_user.user.id, action="drift_monitor", from_status=model.status, to_status=model.status, reason="Model drift evaluation", payload=result))
    await db.commit()
    return {"model_version_id": model.id, **result}
