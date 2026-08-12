"""Versioned agriculture report snapshot construction."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

REPORT_TEMPLATE_VERSION = "1.0"
DECISION_REPORT_TEMPLATE_VERSION = "decision_v1"


def _checksum(payload: dict[str, Any]) -> str:
    canonical_snapshot = {key: value for key, value in payload.items() if key != "captured_at"}
    canonical = json.dumps(
        canonical_snapshot,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def build_report_snapshot(
    *,
    run: Any,
    observations: list[Any],
    layers: list[Any],
    template_key: str,
) -> tuple[dict[str, Any], str]:
    """Build deterministic report data from one point-in-time query result."""
    by_type: dict[str, int] = {}
    by_review: dict[str, int] = {}
    features: list[dict[str, Any]] = []
    for row in observations:
        observation_type = str(row.observation_type)
        review_state = str(row.review_state)
        by_type[observation_type] = by_type.get(observation_type, 0) + 1
        by_review[review_state] = by_review.get(review_state, 0) + 1
        features.append(
            {
                "type": "Feature",
                "geometry": row.geometry_geojson or {},
                "properties": {
                    "id": row.id,
                    "issue_type": observation_type,
                    "severity": row.severity,
                    "confidence": row.confidence,
                    "review_state": review_state,
                    "model_version": row.model_version,
                    "provenance": getattr(row, "provenance", {}) or {},
                    "source_ids": list(
                        getattr(row, "source_ids", None)
                        or getattr(row, "evidence_ids", [])
                    ),
                    "uncertainty": row.uncertainty or {},
                },
            }
        )
    snapshot = {
        "schema_version": "agriculture-report-v1",
        "template_key": template_key,
        "template_version": REPORT_TEMPLATE_VERSION,
        "run_id": run.id,
        "flight_id": run.flight_id,
        "status": run.status,
        "progress": run.progress,
        "quality_gate": run.quality_gate or {},
        "counters": run.counters or {},
        "model_versions": run.model_versions or {},
        "calibration_versions": run.calibration_versions or {},
        "summary": {
            "observation_count": len(observations),
            "by_type": by_type,
            "by_review_state": by_review,
            "confirmed_count": by_review.get("confirmed", 0),
            "unreviewed_count": by_review.get("unreviewed", 0),
            "layer_names": [layer.layer_name for layer in layers],
        },
        "layers": [
            {
                "name": layer.layer_name,
                "status": layer.status,
                "checksum": layer.checksum,
                "summary": layer.summary or {},
            }
            for layer in layers
        ],
        "features": features,
        "limitations": [
            "RGB candidate outputs require human review and validated model evidence.",
            "This report is not treatment advice or a substitute for agronomic inspection.",
        ],
        "captured_at": datetime.now(UTC).isoformat(),
    }
    return snapshot, _checksum(snapshot)


def build_decision_report_snapshot(
    *,
    field: Any,
    current_flight: Any,
    reference_flight: Any | None,
    current_run: Any,
    reference_run: Any | None,
    comparability: dict[str, Any],
    changes: list[Any],
    reviewed_observations: list[Any],
    approved_actions: list[Any],
    findings: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str]:
    """Concise shareable decision report for repeat-flight comparison."""
    prioritized_changes = sorted(
        changes,
        key=lambda row: (
            0 if getattr(row, "state", None) in {"new", "expanding"} else 1,
            -float(getattr(row, "confidence", 0) or 0),
            str(getattr(row, "id", "")),
        ),
    )
    change_features = []
    for row in prioritized_changes[:50]:
        change_features.append(
            {
                "type": "Feature",
                "geometry": getattr(row, "geometry_geojson", None) or {},
                "properties": {
                    "id": getattr(row, "id", None),
                    "issue_type": getattr(row, "observation_type", None),
                    "state": getattr(row, "state", None),
                    "severity": getattr(row, "delta_intensity", None),
                    "confidence": getattr(row, "confidence", None),
                    "status": getattr(row, "state", None),
                    "source_ids": list(getattr(row, "evidence_ids", None) or []),
                    "current_observation_id": getattr(row, "current_observation_id", None),
                    "previous_observation_id": getattr(row, "previous_observation_id", None),
                    "uncertainty": getattr(row, "uncertainty", None) or {},
                },
            }
        )
    reviewed_evidence = [
        {
            "observation_id": row.id,
            "review_state": row.review_state,
            "observation_type": row.observation_type,
            "evidence_ids": list(row.evidence_ids or []),
            "model_version": row.model_version,
            "confidence": row.confidence,
            "severity": row.severity,
        }
        for row in reviewed_observations
        if row.review_state in {"confirmed", "rejected", "relabelled"}
    ]
    approved_action_rows = [
        {
            "id": row.id,
            "issue_type": row.issue_type,
            "priority_rank": row.priority_rank,
            "status": row.status,
            "severity": row.severity,
            "confidence": row.confidence,
            "source_ids": list(row.source_ids or []),
            "waypoint_geojson": row.waypoint_geojson or {},
        }
        for row in approved_actions
        if row.status == "approved"
    ]
    snapshot = {
        "schema_version": "agriculture-decision-report-v1",
        "template_key": "decision",
        "template_version": DECISION_REPORT_TEMPLATE_VERSION,
        "field_context": {
            "field_id": getattr(field, "id", None),
            "name": getattr(field, "name", None),
            "crop_type": (getattr(current_flight, "profile_snapshot", None) or {}).get("crop_type"),
            "season": getattr(current_flight, "season", None)
            or (getattr(current_flight, "profile_snapshot", None) or {}).get("season"),
            "growth_stage": (getattr(current_flight, "profile_snapshot", None) or {}).get("growth_stage"),
        },
        "comparable_inputs": {
            "current_flight_id": current_flight.id,
            "reference_flight_id": getattr(reference_flight, "id", None),
            "current_run_id": current_run.id,
            "reference_run_id": getattr(reference_run, "id", None),
            "comparability": comparability,
            "current_model_versions": current_run.model_versions or {},
            "reference_model_versions": getattr(reference_run, "model_versions", None) or {},
            "current_calibration_versions": current_run.calibration_versions or {},
            "reference_calibration_versions": getattr(reference_run, "calibration_versions", None) or {},
        },
        "prioritized_changes": [
            {
                "id": item["properties"]["id"],
                "state": item["properties"]["state"],
                "issue_type": item["properties"]["issue_type"],
                "confidence": item["properties"]["confidence"],
                "source_ids": item["properties"]["source_ids"],
            }
            for item in change_features
        ],
        "prioritized_findings": findings or [],
        "reviewed_evidence": reviewed_evidence,
        "approved_actions": approved_action_rows,
        "features": change_features,
        "summary": {
            "change_count": len(changes),
            "reviewed_evidence_count": len(reviewed_evidence),
            "approved_action_count": len(approved_action_rows),
            "comparability_score": (comparability or {}).get("score"),
            "comparability_status": (comparability or {}).get("status"),
        },
        "provenance_appendix": {
            "current_run_checksum_inputs": {
                "model_versions": current_run.model_versions or {},
                "calibration_versions": current_run.calibration_versions or {},
                "quality_gate": current_run.quality_gate or {},
            },
            "reference_run_checksum_inputs": {
                "model_versions": getattr(reference_run, "model_versions", None) or {},
                "calibration_versions": getattr(reference_run, "calibration_versions", None) or {},
                "quality_gate": getattr(reference_run, "quality_gate", None) or {},
            },
            "comparability_policy": (comparability or {}).get("policy_version"),
            "warnings": list((comparability or {}).get("warnings") or []),
            "blockers": list((comparability or {}).get("blockers") or []),
        },
        "limitations": [
            "Decision reports summarize reviewed evidence and approved actions only.",
            "Incompatible model, sensor, or calibration inputs never produce silent deltas.",
            "This report is not treatment advice.",
        ],
        "captured_at": datetime.now(UTC).isoformat(),
    }
    return snapshot, _checksum(snapshot)
