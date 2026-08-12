# EXP-001 safety & support ownership

| Concern | Owner | Backup | Notes |
|---|---|---|---|
| Calibration artifact integrity | Platform / Agriculture backend | Vision ops | Checksum + validity window |
| Spectral gate correctness | Agriculture fusion maintainers | — | `validate_spectral_inputs` |
| Agronomy rule approval | Customer agronomist + org admin | Product owner | No auto-approve |
| Prescription content (inspection-only) | Agronomist | Product | Rates forbidden without regulatory reference |
| Export approval & audit | Org reviewer | Compliance | Governance audit required |
| Downstream machine consumer validation | Integrations + customer ops | — | Blocking for machine GO |
| Support burden for MS sensors | Support lead | Agriculture PM | Panel/DLS training required |
| Incident / misuse (false treatment) | Safety reviewer | Legal | Threat review in threat-safety-review.md |

## Agreement statement

Until ADR-003 is GO:

- Support will not promise NDVI maps or rate prescriptions as product features.
- Engineering will keep multispectral/prescription **research-blocked** in the
  capability catalog.
- Exports remain human-approved and inspection-oriented.
