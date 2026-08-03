"""Versioned agriculture report snapshot construction."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

REPORT_TEMPLATE_VERSION = "1.0"


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
                    "source_ids": list(row.source_ids or []),
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
    # Capture time is useful display metadata but must not alter the content identity.
    canonical_snapshot = {key: value for key, value in snapshot.items() if key != "captured_at"}
    canonical = json.dumps(
        canonical_snapshot,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return snapshot, hashlib.sha256(canonical).hexdigest()
