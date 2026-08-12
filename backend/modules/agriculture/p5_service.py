"""Release 5 deterministic action, prescription and export orchestration."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shapely.geometry import mapping

from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureFlight, AgricultureObservation
from backend.modules.agriculture.p4_models import AgricultureCropRisk
from backend.modules.agriculture.p5_models import AgricultureAgronomyRule, AgricultureExportAccessAudit, AgricultureExportJob, AgricultureGovernanceAudit, AgricultureInspectionAction, AgriculturePrescriptionDraft, AgricultureReportSnapshot
from backend.modules.agriculture.p5_policy import build_csv, build_geojson, build_pdf, build_shapefile_zip, plan_inspection_waypoints
from backend.modules.agriculture.storage import agriculture_storage


class AgricultureSafetyService:
    async def _audit(self, db: AsyncSession, *, org_id: int | None, entity_type: str, entity_id: str, user_id: int | None, action: str, from_status: str | None, to_status: str | None, reason: str | None = None, payload: dict[str, Any] | None = None) -> None:
        db.add(AgricultureGovernanceAudit(org_id=org_id, entity_type=entity_type, entity_id=entity_id, actor_user_id=user_id, action=action, from_status=from_status, to_status=to_status, reason=reason, payload=payload or {}))

    async def inspection_plan(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, field: Any, request: dict[str, Any]) -> dict[str, Any]:
        risks = list((await db.scalars(select(AgricultureCropRisk).where(AgricultureCropRisk.run_id == run.id, AgricultureCropRisk.review_state == "confirmed"))).all())
        observations = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == run.id, AgricultureObservation.review_state == "confirmed"))).all())
        candidates = [{"id": row.id, "issue_type": row.issue_type, "geometry_geojson": row.geometry_geojson, "severity": row.severity, "confidence": row.confidence, "area_m2": row.area_m2, "source_ids": [row.id], "rationale": "Confirmed crop-risk evidence"} for row in risks]
        candidates.extend({"id": row.id, "issue_type": row.observation_type, "geometry_geojson": row.geometry_geojson, "severity": row.severity, "confidence": row.confidence, "area_m2": row.area_m2, "source_ids": [row.id], "rationale": "Confirmed agriculture observation"} for row in observations)
        boundary = mapping(to_shape(field.boundary)) if getattr(field, "boundary", None) is not None else request.get("field_boundary_geojson")
        planned = plan_inspection_waypoints(candidates, field_boundary=boundary or {}, no_go_geometries=request.get("no_go_geometries", []), max_actions=int(request.get("max_actions", 50)), battery_budget_s=request.get("battery_budget_s"), seconds_per_action=float(request.get("seconds_per_action", 90)))
        output=[]
        if planned["status"] == "ready":
            existing_actions = list((await db.scalars(select(AgricultureInspectionAction).where(AgricultureInspectionAction.run_id == run.id))).all())
            for item in planned["actions"]:
                action = next((row for row in existing_actions if item["id"] in (row.source_ids or [])), None)
                if action is None: action = AgricultureInspectionAction(run_id=run.id, flight_id=flight.id, field_id=flight.field_id, issue_type=item["issue_type"]); db.add(action)
                action.source_ids=item["source_ids"]; action.priority_rank=item["priority_rank"]; action.priority_score=float(item["severity"])*float(item["confidence"]); action.severity=item["severity"]; action.confidence=item["confidence"]; action.area_m2=item.get("area_m2"); action.geometry_geojson=item["geometry_geojson"]; action.waypoint_geojson=item["waypoint_geojson"]; action.rationale=item["rationale"]; action.route_constraints=planned["constraints"]; action.uncertainty={"policy": "confirmed evidence only", "rejected_count": len(planned["rejected"])}; action.status="draft"; output.append(action)
        await db.commit()
        return {"status": planned["status"], "actions": output, "rejected": planned["rejected"], "constraints": planned["constraints"], "source_count": len(candidates)}

    async def review_action(self, db: AsyncSession, *, action: AgricultureInspectionAction, status: str, note: str | None, user_id: int | None, org_id: int | None) -> AgricultureInspectionAction:
        previous=action.status; action.status=status; action.review_note=note; action.reviewed_by_user_id=user_id; action.reviewed_at=datetime.now(UTC); await self._audit(db, org_id=org_id, entity_type="inspection_action", entity_id=action.id, user_id=user_id, action="review", from_status=previous, to_status=status, reason=note); await db.commit(); await db.refresh(action); return action

    async def update_inspection_route(
        self,
        db: AsyncSession,
        *,
        run: AgricultureAnalysisRun,
        ordered_action_ids: list[str],
        removed_action_ids: list[str],
        reason: str | None,
        user_id: int | None,
        org_id: int | None,
    ) -> list[AgricultureInspectionAction]:
        actions = list(
            (
                await db.scalars(
                    select(AgricultureInspectionAction).where(AgricultureInspectionAction.run_id == run.id)
                )
            ).all()
        )
        by_id = {row.id: row for row in actions}
        missing = [action_id for action_id in [*ordered_action_ids, *removed_action_ids] if action_id not in by_id]
        if missing:
            raise ValueError(f"unknown_inspection_actions:{','.join(missing)}")
        for rank, action_id in enumerate(ordered_action_ids, start=1):
            action = by_id[action_id]
            previous_rank = action.priority_rank
            action.priority_rank = rank
            if previous_rank != rank:
                await self._audit(
                    db,
                    org_id=org_id,
                    entity_type="inspection_action",
                    entity_id=action.id,
                    user_id=user_id,
                    action="route_reordered",
                    from_status=str(previous_rank),
                    to_status=str(rank),
                    reason=reason,
                    payload={"priority_rank": rank},
                )
        for action_id in removed_action_ids:
            action = by_id[action_id]
            previous = action.status
            if previous == "rejected":
                continue
            action.status = "rejected"
            action.review_note = reason or action.review_note
            action.reviewed_by_user_id = user_id
            action.reviewed_at = datetime.now(UTC)
            await self._audit(
                db,
                org_id=org_id,
                entity_type="inspection_action",
                entity_id=action.id,
                user_id=user_id,
                action="route_removed",
                from_status=previous,
                to_status="rejected",
                reason=reason,
            )
        await db.commit()
        return list(
            (
                await db.scalars(
                    select(AgricultureInspectionAction)
                    .where(AgricultureInspectionAction.run_id == run.id)
                    .order_by(AgricultureInspectionAction.priority_rank)
                )
            ).all()
        )

    async def register_rule(self, db: AsyncSession, *, payload: dict[str, Any], org_id: int | None, user_id: int | None) -> AgricultureAgronomyRule:
        rule=AgricultureAgronomyRule(org_id=org_id, created_by_user_id=user_id, **payload); db.add(rule); await db.commit(); await db.refresh(rule); return rule

    async def prescription(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, request: dict[str, Any]) -> AgriculturePrescriptionDraft:
        rule=await db.get(AgricultureAgronomyRule, request.get("rule_id")) if request.get("rule_id") else None
        risks=list((await db.scalars(select(AgricultureCropRisk).where(AgricultureCropRisk.run_id == run.id, AgricultureCropRisk.review_state == "confirmed", AgricultureCropRisk.confidence >= float(request.get("minimum_confidence", .6))))).all())
        status="draft"; assumptions=["Only confirmed multimodal observations are eligible", "No chemical or fertilizer rate is generated"]
        blocked=[]
        if rule is None: blocked.append("approved_rule_required")
        elif rule.status != "approved": blocked.append("rule_not_approved")
        elif rule.action_kind != "inspection_only" and not rule.regulatory_reference: blocked.append("regulatory_reference_required_for_regulated_action")
        if not risks: blocked.append("no_confirmed_multimodal_observations")
        zones=[]
        if not blocked:
            for risk in risks: zones.append({"type": "Feature", "geometry": risk.geometry_geojson, "properties": {"source_id": risk.id, "issue_type": risk.issue_type, "confidence": risk.confidence, "severity": risk.severity, "action_kind": rule.action_kind, "rule_key": rule.rule_key, "rule_version": rule.version}})
        if blocked: status="blocked"
        existing=await db.scalar(select(AgriculturePrescriptionDraft).where(AgriculturePrescriptionDraft.run_id == run.id, AgriculturePrescriptionDraft.rule_id == (rule.id if rule else None)))
        if existing is None: existing=AgriculturePrescriptionDraft(run_id=run.id, flight_id=flight.id, field_id=flight.field_id, rule_id=rule.id if rule else None); db.add(existing)
        existing.status=status; existing.zones=zones; existing.source_ids=[risk.id for risk in risks]; existing.rule_provenance={"rule_id": rule.id, "rule_key": rule.rule_key, "version": rule.version, "jurisdiction": rule.jurisdiction} if rule else {}; existing.model_provenance={"source": "confirmed_crop_risks", "model_versions": sorted({risk.model_version for risk in risks if risk.model_version})}; existing.assumptions=assumptions + blocked; existing.confidence=sum(risk.confidence for risk in risks)/len(risks) if risks else 0.0; existing.uncertainty={"blocked_reasons": blocked, "requires_human_approval": True}; await db.commit(); return existing

    async def review_prescription(self, db: AsyncSession, *, draft: AgriculturePrescriptionDraft, status: str, note: str | None, user_id: int | None, org_id: int | None) -> AgriculturePrescriptionDraft:
        previous=draft.status; draft.status=status; draft.review_note=note; draft.reviewed_by_user_id=user_id; draft.reviewed_at=datetime.now(UTC); await self._audit(db, org_id=org_id, entity_type="prescription", entity_id=draft.id, user_id=user_id, action="review", from_status=previous, to_status=status, reason=note); await db.commit(); await db.refresh(draft); return draft

    async def create_export(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, request: dict[str, Any], user_id: int | None, org_id: int | None) -> AgricultureExportJob:
        artifact_kind=request["artifact_kind"]; fmt=request["format"]
        if fmt not in {"geojson", "csv", "shapefile", "pdf"}: raise ValueError("unsupported_export_format")
        features=[]; source_ids=[]; approved_source_id=request.get("source_id"); report_metadata: dict[str, Any] = {}
        if artifact_kind == "inspection_actions":
            actions=list((await db.scalars(select(AgricultureInspectionAction).where(AgricultureInspectionAction.run_id == run.id, AgricultureInspectionAction.status == "approved"))).all()); source_ids=[row.id for row in actions]; features=[{"type":"Feature", "geometry": row.waypoint_geojson, "properties": {"id": row.id, "issue_type": row.issue_type, "severity": row.severity, "confidence": row.confidence, "status": row.status, "source_ids": row.source_ids}} for row in actions]
            if not actions: raise ValueError("approved_inspection_action_required")
        elif artifact_kind == "prescription":
            draft=await db.get(AgriculturePrescriptionDraft, approved_source_id) if approved_source_id else None
            if draft is None or draft.status != "approved": raise ValueError("approved_prescription_required")
            source_ids=[draft.id, *draft.source_ids]; features=draft.zones
        elif artifact_kind == "report":
            snapshot = await db.get(AgricultureReportSnapshot, approved_source_id) if approved_source_id else None
            if snapshot is None or snapshot.run_id != run.id or snapshot.org_id != org_id:
                raise ValueError("report_snapshot_required")
            snapshot_json = snapshot.snapshot_json or {}
            features = list(snapshot_json.get("features", []))
            if not features and snapshot.template_key == "decision":
                for action in snapshot_json.get("approved_actions") or []:
                    waypoint = action.get("waypoint_geojson") or {}
                    if not waypoint:
                        continue
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": waypoint,
                            "properties": {
                                "id": action.get("id"),
                                "issue_type": action.get("issue_type"),
                                "severity": action.get("severity"),
                                "confidence": action.get("confidence"),
                                "status": action.get("status"),
                                "source_ids": action.get("source_ids") or [],
                                "priority_rank": action.get("priority_rank"),
                            },
                        }
                    )
                if not features:
                    for change in snapshot_json.get("prioritized_changes") or []:
                        features.append(
                            {
                                "type": "Feature",
                                "geometry": {},
                                "properties": {
                                    "id": change.get("id"),
                                    "issue_type": change.get("issue_type"),
                                    "state": change.get("state"),
                                    "confidence": change.get("confidence"),
                                    "status": change.get("state"),
                                    "source_ids": change.get("source_ids") or [],
                                },
                            }
                        )
            source_ids = [str(item.get("properties", {}).get("id")) for item in features if item.get("properties", {}).get("id")]
            report_metadata = {"template_key": snapshot.template_key, "template_version": snapshot.template_version, "summary": snapshot_json.get("summary", {})}
            if not features:
                raise ValueError("report_snapshot_has_no_features")
        else:
            risks=list((await db.scalars(select(AgricultureCropRisk).where(AgricultureCropRisk.run_id == run.id, AgricultureCropRisk.review_state == "confirmed"))).all()); observations=list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == run.id, AgricultureObservation.review_state == "confirmed"))).all()); source_ids=[row.id for row in risks]+[row.id for row in observations]; features=[{"type":"Feature", "geometry": row.geometry_geojson, "properties": {"id": row.id, "issue_type": getattr(row, "issue_type", getattr(row, "observation_type", "observation")), "severity": row.severity, "confidence": row.confidence, "status": "confirmed", "source_ids": [row.id]}} for row in [*risks,*observations]]
            if not features: raise ValueError("confirmed_observation_required")
        payload={"type":"FeatureCollection", "features":features, "metadata":{"field_id":flight.field_id, "flight_id":flight.id, "run_id":run.id, "source_ids":source_ids, "quality":run.quality_gate or {}, "input_manifest":flight.input_manifest or {}, "report_snapshot_id": approved_source_id if artifact_kind == "report" else None, "generated_at":datetime.now(UTC).isoformat(), "uncertainty":"Source observations retain their recorded uncertainty; no new certainty is introduced.", **report_metadata}}
        job=AgricultureExportJob(org_id=org_id, field_id=flight.field_id, flight_id=flight.id, run_id=run.id, artifact_kind=artifact_kind, format=fmt, status="running", source_manifest=payload["metadata"], requested_by_user_id=user_id, expires_at=datetime.now(UTC)+timedelta(hours=24)); db.add(job); await db.flush()
        data=build_geojson(payload) if fmt=="geojson" else build_csv(payload) if fmt=="csv" else build_shapefile_zip(payload) if fmt=="shapefile" else build_pdf(payload); extension="zip" if fmt=="shapefile" else fmt; key=f"org/{org_id if org_id is not None else 'public'}/exports/{job.id}.{extension}"; agriculture_storage.validate_tenant_key(key, org_id=org_id, resource="exports"); job.checksum=hashlib.sha256(data).hexdigest(); agriculture_storage.write_object(key, data, expected_checksum=job.checksum); job.storage_key=key; job.content_type={"geojson":"application/geo+json","csv":"text/csv","shapefile":"application/zip","pdf":"application/pdf"}[fmt]; job.status="ready"; await self._audit(db, org_id=org_id, entity_type="export", entity_id=job.id, user_id=user_id, action="created", from_status="running", to_status="ready", payload={"format":fmt,"artifact_kind":artifact_kind}); await db.commit(); await db.refresh(job); return job

    async def access_export(self, db: AsyncSession, *, job: AgricultureExportJob, user_id: int | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        now=datetime.now(UTC)
        if job.status != "ready" or not job.storage_key: raise ValueError("export_not_ready")
        if job.expires_at and job.expires_at < now: job.status="expired"; await db.commit(); raise ValueError("export_expired")
        db.add(AgricultureExportAccessAudit(export_id=job.id, actor_user_id=user_id, action="signed_url", metadata_json=metadata or {})); await db.commit(); return {"id":job.id,"status":job.status,"format":job.format,"checksum":job.checksum,"expires_at":job.expires_at,"download_url":agriculture_storage.sign(job.storage_key, expires_in=900)}


agriculture_safety_service = AgricultureSafetyService()
