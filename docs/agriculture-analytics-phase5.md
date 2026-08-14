# Phase 5 agriculture analytics contracts

Phase 5 adds operational analytics only when the run contains enough geometry,
crop context, and calibrated sensor evidence to support the requested unit or
claim. Missing prerequisites produce `blocked`, `warning`, or `not_measured`
outputs; they are never replaced with generic agronomic assumptions.

## Stand gaps and plant spacing

Stand analytics use georeferenced plant centres and local WGS84 metric
projection. Video detections are deduplicated by job/track when tracking is
available. Gap classification additionally requires:

- a named crop;
- row direction and expected row spacing;
- expected within-row plant spacing; and
- an explicit gap multiplier.

The field/mission profile owns these values. The run emits `stand_gap` polygon
observations and layers with affected row, length, area, estimated missing
plants, severity, confidence, evidence IDs, and the frozen assumptions. The
`plant_spacing` layer reports global and row-level median spacing, IQR, median
absolute deviation, and statistical outliers. Metric spacing is withheld when
row geometry or georeferenced plant centres are unavailable.

## Weed density

The `weed_density` product intersects a configurable metric grid with the field
boundary and reports unique weed detections per square metre. Non-empty cells
include their field-wide percentile and descending density rank. Cells at or
above the configured percentile become `weed_density_hotspot` observations.
When the run names a same-field baseline with matching crop/sensor context and
acceptable quality, the summary includes the density delta; otherwise it states
that no comparable baseline was used.

## Segmentation experiment

`POST /agriculture/analysis-runs/{run_id}/analytics/segmentation-experiment`
evaluates a crop-specific holdout result against the detection approximation.
The gate requires at least 300 labeled images, 1,000 instances, three
independent fields, a holdout/test/shadow split, and a dataset checksum. Benefit
requires candidate weed-zone IoU of at least 0.60, an absolute IoU gain of 0.05,
and at least 10% relative area-error improvement.

The persisted layer is always `research_only`; even a passing experiment has
`production_eligible: false`. A separate architecture and safety review is
required before enabling any production segmentation path.

## Crop-specific plugins

`fruit_counting` and `ripeness_classification` are detection-backed Vision
capabilities, not generic RGB promises. Production activation requires a named
crop, explicit classes, crop-specific overall and per-class holdout thresholds,
and the recorded model/dataset/checksum lineage. Readiness also enforces the
capability's GSD, camera calibration, orientation, and (for ripeness) growth
stage conditions. Release snapshots expose confidence/evaluation thresholds,
supported capture conditions, and limitations. Ripeness never applies to an
unlisted crop or arbitrary RGB capture.

## Multispectral and thermal

NDVI, GNDVI, and NDRE use strict band maps (`red+nir`, `green+nir`, and
`red_edge+nir`). Each required band must include plausible wavelength metadata,
sensor serial, current matching calibration, reflectance-panel evidence,
alignment, and passing band quality. RGB flights expose RGB metrics separately
and never synthesize a vegetation index.

Thermal output requires a registered, current, serial-matched radiometric
calibration plus ambient air temperature. Relative humidity and wind are
retained as contextual warnings when absent. The output is a canopy-temperature
stress candidate relative to ambient conditions, never a disease diagnosis.

ADR-003 still prohibits a general production `multispectral` or thermal-stress
capability label. These calibrated sensor products remain input-gated analytics
and do not change that release decision.
