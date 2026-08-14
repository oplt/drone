# Architecture Phase 0 — lock-in rules

Recorded: 2026-08-14

Phase 0 establishes guardrails before large file splits (see `prompt.txt`). Do not
mix behavioral changes with architecture extraction in the same PR.

## CI gates (enabled)

| Gate | Command |
| --- | --- |
| Backend file size | `python backend/scripts/check_file_sizes.py` |
| Frontend file size | `cd frontend && npm run check:arch` |
| Characterization registry | `python backend/scripts/check_characterization_registry.py` |

Also run via `make backend-guardrails` and `make frontend-quality`.

## File-size rules

1. **No new violations** — files over their category limit fail CI unless grandfathered.
2. **No regressions** — grandfathered files may not grow beyond their baseline effective-line count.
3. **Prune on resolve** — when a file drops to or below its limit, remove its baseline entry:

   ```bash
   python backend/scripts/check_file_sizes.py --prune-baseline
   cd frontend && node scripts/check_file_sizes.mjs --prune-baseline
   ```

4. **Excluded from metrics** — applied Alembic revisions and `backend/tests/` (golden/characterization tests may exceed module limits).

### Category limits

**Backend**

| Path pattern | Limit |
| --- | ---: |
| API routers / `api.py` | 220 |
| Repositories / models | 250 |
| Services / application | 300 |
| Infrastructure | 260 |
| Default module | 400 |

**Frontend**

| Path pattern | Limit |
| --- | ---: |
| `views/` / `pages/` | 180 |
| `hooks/` | 160 |
| `components/` | 220 |
| `api/` | 220 |
| Default source | 400 |

Effective lines = non-blank, non–whole-line-comment lines.

## Characterization tests before splits

Behavior-heavy modules listed in `backend/scripts/characterization_registry.json`
must have registered tests **before** structural extraction begins.

Workflow for a split PR:

1. Add or extend golden/contract tests for the module (routes, coordinates, state transitions).
2. Register test paths in `characterization_registry.json`.
3. Run `python backend/scripts/check_characterization_registry.py`.
4. Split files without changing observable behavior.
5. Run `--prune-baseline` for any file that now meets its limit.

## PR policy

- **One concern per PR** — either behavior/fix **or** architecture extraction, not both.
- **Tests first** for algorithmic modules (planning, structure extraction, MAVLink).
- **Preserve contracts** — endpoint URLs, Pydantic schemas, WebSocket wire formats, public imports.
- **Update baseline only** via `--update-baseline` when deliberately recording new grandfathered debt (avoid in normal feature PRs).

## Roadmap pointer

| Phase | Focus |
| ---: | --- |
| 0 | Rules + CI (this document) |
| 1 | Frontend god pages |
| 2 | Backend API routers |
| 3 | Planning algorithms |
| 4 | Infrastructure runtimes |
| 5 | Map/telemetry rendering |
| 6 | Warehouse structure pipeline |

Highest-value sequence: `Warehouse.tsx` → `missions/api/routes.py` → private patrol → `structure_jobs.py` → `patrol/planning.py` → `CesiumMap.tsx` → `mavlink_client.py` → warehouse scan/structure/live-map.
