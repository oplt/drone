# EXP-001 hardware & integration matrix

| Item | Decision for research | Notes |
|---|---|---|
| Primary MS sensor | MicaSense RedEdge-P class (5-band + panel) | Representative of panel + irradiance workflows |
| Secondary MS | DJI Mavic 3M | Common customer ask; DLS optional |
| Bands required for NDVI | `red`, `nir` | Alignment + quality + calibration + panel required |
| Bands for GNDVI | `green`, `nir` | Same gates |
| Calibration package | Immutable artifact: serial, version, checksum, valid window | Matches `AgricultureSensorCalibration` |
| Reflectance panel | Per-flight panel spectrum in band metadata | Missing panel blocks indices |
| Irradiance | Optional DLS values stored on band rows | Absence recorded in uncertainty, not silent fill |
| Index CRS | EPSG:4326 for research fixtures | Machine CRS TBD per consumer |
| Prescription format (research) | GeoJSON zones + WGS84 shapefile zip | Attributes: issue_type, confidence, severity, action_kind=`inspection_only` |
| Machine format (blocked) | ISOXML / TaskData | Stub checklist only; no production exporter |
| Downstream consumer for GO | Real controller/import of shapefile or ISOXML | Required for machine-prescription GO; not satisfied by unit zip members alone |

## Known failure modes

- Flying without panel → blocked NDVI (correct)
- Band length mismatch → blocked index
- Unapproved agronomy rule → blocked prescription
- Exporting rates without regulatory reference → blocked
- Marketing NDVI as available while gates fail → product/safety risk (label hygiene)
