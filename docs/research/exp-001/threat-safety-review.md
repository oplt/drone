# EXP-001 threat & safety review (research)

## Threats

1. **False confidence**: Presenting uncalibrated RGB stress as NDVI.
2. **Treatment misuse**: Exporting zones interpreted as chemical rates.
3. **Silent gate bypass**: Override compares / fusion without panel.
4. **Consumer mismatch**: Shapefile loads in GIS but fails Task Controller.
5. **Label debt**: Roadmap/marketing implying available MS products.

## Mitigations in this slice

- Calibration/alignment/quality/panel gates in `validate_spectral_inputs`
- Prescription requires approved rule; no rates by default
- Human approval before export
- Research ADR outcome **DEFER / NO-GO** for production MS & machine prescription
- Label hygiene: readiness roadmap marks research-blocked; marketing copy softened

## Residual risk

Field agronomic false negatives/positives on real MS data are unknown until
multi-field validation. Machine ISOXML contract is unproven.

## Verdict for research exit

Safe to continue **offline research and RGB production path**. Unsafe to enable
production multispectral or machine-prescription capability labels.
