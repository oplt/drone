## Summary
-

## Test plan
- [ ] Unit: Top-10 chrome (`TelemetryLinkChip`, `MenuContent`, `DashboardAlertsPanel`)
- [ ] Agri UI (if agriculture/video UI touched): `AgricultureReviewWorkspace`, `AgricultureTemporalWorkspace`, `CaptureMetadataEditor`, `HealthLayerSwitcher`
- [ ] Labeling mobile gate / VideoAnalysisPanel tab ids when those surfaces change
- [ ] `npm run check:telemetry-ui-budget` if telemetry stream notify rate changes
- [ ] Playwright chromium smoke (`ops-primary-journey`) when shell/IA/nav changes
- [ ] Optional: `E2E_VISUAL=1 npm run test:e2e -- e2e/visual` after theme token changes
