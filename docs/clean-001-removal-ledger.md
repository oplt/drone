# CLEAN-001 removal ledger

## Removed

### `agriculture:evidence-select` compatibility listener

- Removed from `VideoAnalysisPanel.tsx`.
- Proof: repository search found no event dispatchers. Both Agriculture evidence
  consumers call the typed `selectDetectionEvidence` URL-state helper directly
  (`AgricultureReviewWorkspace.tsx` and `AgricultureTemporalWorkspace.tsx`).
- Retained path: `evidenceSelection.ts` owns selection and browser-history state.

### Permanent capability alias remapping table

- Replaced the old alias-to-canonical mapping branch with a retired-ID rejection
  set. No request is remapped.
- Proof: the P0 contract test asserts retired IDs fail and canonical capability
  IDs continue to pass.

## Retained pending production data scan

### Vision `instance_segmentation` database value

- New API requests reject `instance_segmentation` with an explicit detection-only
  validation error. The public create schema exposes only `detection`.
- The database check-constraint value and existing annotation persistence columns
  are retained. There is no verified production row inventory proving a
  destructive migration safe.
- Removal requires a tenant-by-tenant data scan, export/quarantine plan for any
  matching rows, and a separately reviewed migration.

## INVESTIGATE

### npm dependencies

No package is nominated for removal in this slice. Static source search alone is
not exhaustive proof because Vite plugins, dynamic imports, CSS integration, and
build scripts can consume packages without ordinary TypeScript imports. A future
removal must include lockfile, build configuration, dynamic usage, production
build, focused tests, and bundle verification evidence.
