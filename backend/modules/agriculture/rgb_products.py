"""Safe, deterministic RGB product contracts.

RGB fallbacks are useful for triage, but they are never promoted to validated
agronomic claims without a registered, evaluated model and human review.
"""

from __future__ import annotations

from typing import Any, Iterable


RGB_PRODUCT_SPECS: dict[str, dict[str, Any]] = {
    "row_detection": {"label": "Crop-row structure", "claim": "visible row geometry"},
    "plant_detection": {"label": "Plant detections", "claim": "candidate plant locations"},
    "stand_count": {"label": "Stand count", "claim": "estimated visible plant count"},
    "canopy_cover": {"label": "Canopy cover", "claim": "visible green-pixel proportion"},
    "missing_plant": {"label": "Missing-plant candidates", "claim": "candidate gaps in detected rows"},
    "visible_water": {"label": "Visible water", "claim": "visible water-like RGB signature"},
    "lodging": {"label": "Lodging candidates", "claim": "candidate flattened crop structure"},
    "obstacle": {"label": "Obstacles", "claim": "candidate non-crop object"},
}

_ALIASES = {
    "rows": "row_detection",
    "row_detection": "row_detection",
    "plants": "plant_detection",
    "plant_detection": "plant_detection",
    "stand_count": "stand_count",
    "gaps": "missing_plant",
    "missing_plant": "missing_plant",
    "canopy": "canopy_cover",
    "canopy_cover": "canopy_cover",
    "water": "visible_water",
    "visible_water": "visible_water",
    "lodging": "lodging",
    "obstacle": "obstacle",
}

_LIMITATIONS = (
    "RGB candidate only; not a confirmed disease, nutrient, moisture, yield, or treatment recommendation.",
    "Validate against representative crop/season data and human review before operational use.",
)


def _product(*, name: str, status: str, confidence: float, value: Any = None, reason: str | None = None, evidence_count: int = 0) -> dict[str, Any]:
    spec = RGB_PRODUCT_SPECS[name]
    return {
        "product": name,
        "label": spec["label"],
        "claim": spec["claim"],
        "status": status,
        "claim_status": "candidate" if status == "candidate" else status,
        "publishable": False,
        "model_version": "rgb-heuristic-v1",
        "confidence": max(0.0, min(1.0, float(confidence))),
        "value": value,
        "evidence_count": evidence_count,
        "reason": reason,
        "limitations": list(_LIMITATIONS),
    }


def _labels(detections: Iterable[Any], names: set[str]) -> list[Any]:
    return [row for row in detections if str(getattr(row, "label", "")).lower().replace("-", "_") in names]


def evaluate_rgb_products(*, segmentation: dict[str, Any], row: dict[str, Any], quality: dict[str, Any], detections: Iterable[Any] = (), requested: Iterable[Any] = ()) -> dict[str, dict[str, Any]]:
    """Return one explicit, quality-aware result for each RGB product.

    Requested names are advisory; unsupported/unknown names are omitted so a
    client cannot accidentally render an unimplemented capability as measured.
    """
    requested_names = {_ALIASES.get(str(value).lower().replace("-", "_")) for value in requested}
    requested_names.discard(None)
    names = requested_names if requested_names else set(RGB_PRODUCT_SPECS)
    quality_blocked = str(quality.get("status", "pass")) == "blocked"
    all_detections = list(detections)
    plants = _labels(all_detections, {"plant", "crop", "seedling", "stand"})
    gaps = _labels(all_detections, {"gap", "skip", "missing_plant", "emergence_issue"})
    lodging = _labels(all_detections, {"lodging", "flattened_crop"})
    obstacles = _labels(all_detections, {"obstacle", "vehicle", "person", "animal", "intrusion"})
    output: dict[str, dict[str, Any]] = {}
    for name in sorted(names):
        if quality_blocked:
            output[name] = _product(name=name, status="blocked_quality", confidence=0.0, reason="image_quality_gate_blocked")
        elif name == "row_detection":
            confidence = float(row.get("confidence", 0.0) or 0.0)
            output[name] = _product(name=name, status="candidate" if confidence > 0 else "not_measured", confidence=confidence, value={"direction_deg": row.get("row_direction_deg"), "line_count": row.get("line_count")}, reason=None if confidence > 0 else "row_structure_not_resolved")
        elif name == "plant_detection":
            output[name] = _product(name=name, status="candidate" if plants else "not_measured", confidence=min(0.8, len(plants) / 100), value={"count": len(plants)}, reason=None if plants else "no_plant_detections", evidence_count=len(plants))
        elif name == "stand_count":
            output[name] = _product(name=name, status="candidate" if plants else "not_measured", confidence=min(0.75, len(plants) / 100), value={"estimated_count": len(plants)}, reason=None if plants else "plant_positions_missing", evidence_count=len(plants))
        elif name == "canopy_cover":
            value = segmentation.get("canopy_pct")
            output[name] = _product(name=name, status="candidate" if value is not None else "not_measured", confidence=0.55 if value is not None else 0.0, value={"visible_canopy_pct": value}, reason=None if value is not None else "segmentation_unavailable")
        elif name == "missing_plant":
            output[name] = _product(name=name, status="candidate" if gaps else "not_measured", confidence=min(0.7, len(gaps) / 50), value={"candidate_gap_count": len(gaps)}, reason=None if gaps else "no_gap_detections", evidence_count=len(gaps))
        elif name == "visible_water":
            value = segmentation.get("visible_water_pct")
            output[name] = _product(name=name, status="candidate" if value is not None else "not_measured", confidence=min(0.8, float(value or 0) / 10), value={"visible_water_pct": value}, reason=None if value is not None else "segmentation_unavailable")
        elif name == "lodging":
            output[name] = _product(name=name, status="candidate" if lodging else "not_measured", confidence=min(0.8, len(lodging) / 20), value={"candidate_count": len(lodging)}, reason=None if lodging else "no_lodging_detections", evidence_count=len(lodging))
        elif name == "obstacle":
            output[name] = _product(name=name, status="candidate" if obstacles else "not_measured", confidence=min(0.8, len(obstacles) / 20), value={"candidate_count": len(obstacles)}, reason=None if obstacles else "no_obstacle_detections", evidence_count=len(obstacles))
    return output


def product_gate_summary(products: dict[str, dict[str, Any]], *, evaluated_models: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach explicit model/evaluation gate state to a run."""
    models = evaluated_models or {}
    gated: dict[str, Any] = {}
    for name, result in products.items():
        model = models.get(name) or {}
        validated = bool(model.get("validated"))
        gated[name] = {**result, "validated_model_available": validated, "model_gate": "publishable" if validated else "candidate_only", "model_evidence": model or {"reason": "no_validated_rgb_model"}}
    return gated
