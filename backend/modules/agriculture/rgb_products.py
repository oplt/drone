"""Safe, deterministic RGB product contracts.

RGB fallbacks are useful for triage, but they are never promoted to validated
agronomic claims without a registered, evaluated model and human review.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


RGB_PRODUCT_SPECS: dict[str, dict[str, Any]] = {
    "row_detection": {"label": "Crop-row structure", "claim": "visible row geometry"},
    "object_detection": {"label": "Object detections", "claim": "candidate configured-object locations"},
    "stand_count": {"label": "Stand count", "claim": "estimated visible plant count"},
    "canopy_cover": {"label": "Canopy cover", "claim": "visible green-pixel proportion"},
    "weed_detection": {"label": "Weed detections", "claim": "candidate weed locations"},
    "crop_health": {"label": "Crop-health findings", "claim": "candidate visual crop-health signatures"},
    "standing_water": {"label": "Standing water", "claim": "visible standing-water-like RGB signature"},
    "lodging": {"label": "Lodging candidates", "claim": "candidate flattened crop structure"},
    "obstacle": {"label": "Obstacles", "claim": "candidate non-crop object"},
}

_CAPABILITY_PRODUCTS = {
    "row_detection": "row_detection",
    "object_detection": "object_detection",
    "stand_count": "stand_count",
    "weed_detection": "weed_detection",
    "crop_health": "crop_health",
    "canopy_cover": "canopy_cover",
    "standing_water": "standing_water",
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


def evaluate_rgb_products(*, segmentation: dict[str, Any], row: dict[str, Any], quality: dict[str, Any], detections: Iterable[Any] = (), detection_counts: Mapping[str, int] | None = None, requested: Iterable[Any] = ()) -> dict[str, dict[str, Any]]:
    """Return one explicit, quality-aware result for each RGB product.

    Requested names are advisory; unsupported/unknown names are omitted so a
    client cannot accidentally render an unimplemented capability as measured.
    """
    requested_names = {_CAPABILITY_PRODUCTS.get(str(value).lower().replace("-", "_")) for value in requested}
    requested_names.discard(None)
    names = requested_names
    quality_blocked = str(quality.get("status", "pass")) == "blocked"
    all_detections = list(detections)
    normalized_counts = {
        str(label).lower().replace("-", "_"): int(count)
        for label, count in (detection_counts or {}).items()
    }

    def count_labels(names: set[str]) -> int:
        if detection_counts is not None:
            return sum(normalized_counts.get(name, 0) for name in names)
        return len(_labels(all_detections, names))

    plants = count_labels({"plant", "crop", "seedling", "stand"})
    weeds = count_labels({"weed", "weeds", "vegetation"})
    health = count_labels({"stress", "disease", "damage", "anomaly"})
    lodging = count_labels({"lodging", "flattened_crop"})
    obstacles = count_labels({"obstacle", "vehicle", "person", "animal", "intrusion"})
    output: dict[str, dict[str, Any]] = {}
    for name in sorted(names):
        if quality_blocked:
            output[name] = _product(name=name, status="blocked_quality", confidence=0.0, reason="image_quality_gate_blocked")
        elif name == "row_detection":
            confidence = float(row.get("confidence", 0.0) or 0.0)
            output[name] = _product(name=name, status="candidate" if confidence > 0 else "not_measured", confidence=confidence, value={"direction_deg": row.get("row_direction_deg"), "line_count": row.get("line_count")}, reason=None if confidence > 0 else "row_structure_not_resolved")
        elif name == "object_detection":
            output[name] = _product(name=name, status="candidate" if plants else "not_measured", confidence=min(0.8, plants / 100), value={"count": plants}, reason=None if plants else "no_plant_detections", evidence_count=plants)
        elif name == "stand_count":
            output[name] = _product(name=name, status="candidate" if plants else "not_measured", confidence=min(0.75, plants / 100), value={"estimated_count": plants}, reason=None if plants else "plant_positions_missing", evidence_count=plants)
        elif name == "canopy_cover":
            value = segmentation.get("canopy_pct")
            output[name] = _product(name=name, status="candidate" if value is not None else "not_measured", confidence=0.55 if value is not None else 0.0, value={"visible_canopy_pct": value}, reason=None if value is not None else "segmentation_unavailable")
        elif name == "weed_detection":
            output[name] = _product(name=name, status="candidate" if weeds else "not_measured", confidence=min(0.8, weeds / 50), value={"candidate_count": weeds}, reason=None if weeds else "no_weed_detections", evidence_count=weeds)
        elif name == "crop_health":
            output[name] = _product(name=name, status="candidate" if health else "not_measured", confidence=min(0.8, health / 20), value={"candidate_count": health}, reason=None if health else "no_crop_health_detections", evidence_count=health)
        elif name == "standing_water":
            value = segmentation.get("visible_water_pct")
            output[name] = _product(name=name, status="candidate" if value is not None else "not_measured", confidence=min(0.8, float(value or 0) / 10), value={"visible_water_pct": value}, reason=None if value is not None else "segmentation_unavailable")
        elif name == "lodging":
            output[name] = _product(name=name, status="candidate" if lodging else "not_measured", confidence=min(0.8, lodging / 20), value={"candidate_count": lodging}, reason=None if lodging else "no_lodging_detections", evidence_count=lodging)
        elif name == "obstacle":
            output[name] = _product(name=name, status="candidate" if obstacles else "not_measured", confidence=min(0.8, obstacles / 20), value={"candidate_count": obstacles}, reason=None if obstacles else "no_obstacle_detections", evidence_count=obstacles)
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
