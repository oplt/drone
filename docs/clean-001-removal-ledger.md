# CLEAN-001 removal ledger

## Removed

### `agriculture:evidence-select` compatibility listener

- Removed from `VideoAnalysisPanel.tsx`.
- Proof: repository search found no event dispatchers. Both Agriculture evidence
  consumers call the typed `selectDetectionEvidence` URL-state helper directly
  (`AgricultureReviewWorkspace.tsx` and `AgricultureTemporalWorkspace.tsx`).
- Retained path: `evidenceSelection.ts` owns selection and browser-history state.
- Status: **COMPLETE**

### Permanent capability alias remapping table

- Replaced the old alias-to-canonical mapping branch with a retired-ID rejection
  set. No request is remapped.
- Proof: the P0 contract test asserts retired IDs fail and canonical capability
  IDs continue to pass.
- Status: **COMPLETE**

### Frontend `@fullcalendar/*` packages

- Removed from `frontend/package.json` (and lockfile via `npm uninstall`):
  `@fullcalendar/core`, `@fullcalendar/daygrid`, `@fullcalendar/interaction`,
  `@fullcalendar/list`, `@fullcalendar/timegrid`.
- Proof: `rg '@fullcalendar|FullCalendar|fullcalendar' frontend/src` returned
  zero matches (no static imports, no CSS imports under `src/`).
- Status: **COMPLETE** (2026-08-12)

## Soft-disabled / deferred schema

### Vision `instance_segmentation` database value

- New API requests reject `instance_segmentation` with an explicit detection-only
  validation error. The public create schema exposes only `detection`.
- The database check-constraint value and existing annotation persistence columns
  are retained. Soft-disable remains.
- Inventory script (read-only): `backend/scripts/inventory_instance_segmentation.py`
  counts projects with `task_type=instance_segmentation` and annotations/images
  with non-null `segmentation`.
- **Do not drop** enum/check-constraint values or `segmentation` columns without
  inventory proof of zero rows in every target environment.
- Migration posture: docs/conditional only until inventory reports zeros on
  production; no destructive migration ships in this slice.
- Status: **DEFERRED** (await production inventory proof)

## INVESTIGATE (remaining)

### Other npm dependencies

No further package is nominated for removal in this slice beyond `@fullcalendar/*`.
Static source search alone is not exhaustive proof for other candidates because
Vite plugins, dynamic imports, CSS integration, and build scripts can consume
packages without ordinary TypeScript imports.
