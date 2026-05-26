# Frontend Architecture Baseline (Stage 0)

Recorded: 2026-05-26

This document captures migration guardrails. CI fails on **new** violations; existing debt
is grandfathered in `frontend/scripts/*_baseline.json` until extracted in later stages.

## ESLint baseline (`npm run lint:ci`)

| Module | Findings |
| --- | ---: |
| pages | 109 |
| components | 20 |
| hooks | 20 |
| utils | 18 |
| mission-runtime (tasks) | 16 |
| components/dashboard | 12 |
| lib | 4 |
| **Total** | **199** |

Common categories (fix during module migration, not in bulk here):

- `@typescript-eslint/no-explicit-any`
- `react-hooks/exhaustive-deps`, `react-hooks/set-state-in-effect`, `react-hooks/purity`
- `react-refresh/only-export-components`
- unused variables and invalid eslint-disable comments

Update baseline only when intentionally fixing debt:

```bash
cd frontend
node scripts/check_eslint_baseline.mjs --update-baseline
```

## File-size baseline (`npm run check:arch`)

29 source files exceed category limits (see `frontend/scripts/file_size_baseline.json`).
Largest offenders align with the migration plan:

| File | Effective lines | Limit |
| --- | ---: | ---: |
| `pages/dashboard/tabs/PhotoGrammetry.tsx` | 3,039 | 180 |
| `pages/dashboard/tabs/PrivatePatrolPage.tsx` | 2,776 | 180 |
| `pages/dashboard/tabs/FieldPage.tsx` | 2,503 | 180 |
| `pages/dashboard/tabs/Warehouse.tsx` | 1,271 | 180 |
| `pages/dashboard/tabs/ControlledFlightPage.tsx` | 1,209 | 180 |
| `utils/CesiumMap.tsx` | 1,008 | 180 |
| `components/dashboard/tasks/MissionCommandPanel.tsx` | 687 | 220 |

Update baseline only after shrinking a file or splitting it with tests:

```bash
cd frontend
node scripts/check_file_sizes.mjs --update-baseline
```

## Stage 1 layout (2026-05-26)

```txt
src/
  app/
    config/          env.ts, queryKeys.ts
    providers/       QueryProvider, AppProviders, queryClient
    routes/          AppRouter, ProtectedRoute, GuestRoute, routeLoaders
    App.tsx
  shared/api/        httpClient.ts, apiError.ts
  modules/
    session/         session API, cookies, useSession, useCurrentUser
    dashboard/       analytics API + useAnalyticsOverview (TanStack Query)
```

`main.tsx` is bootstrap-only; the global `window.fetch` patch was removed. Unauthorized
handling for non-auth API calls lives in `shared/api/httpClient.ts`.

## Stage 2 layout (2026-05-26)

```txt
shared/
  theme/           AppTheme, tokens, MUI customizations (charts, data grid, inputs, …)
  layout/          OperationsShell, SideMenu, AppNavbar, PageLayout, ConsoleToolbar, …
  ui/              PageLoader, ErrorState, EmptyState, PermissionDenied, ConfirmDialog
```

- `shared/` does not import `modules/*` (logout is injected via `onLogout` props).
- `components/dashboard/Header.tsx` remains the alerts-aware toolbar wrapper (domain UI).
- Bootstrap / react-bootstrap: still listed in `package.json` but unused in `src/`; Tailwind
  `output.css` remains imported from `main.tsx` until a dedicated removal pass.

Compatibility re-exports remain under `components/shared-theme/`, `components/shared/`, and
`components/dashboard/` for gradual import migration.

## CI commands

```bash
cd frontend
npm run lint:ci          # ESLint baseline guard (no new violations)
npm run check:arch       # file-size baseline guard
npm run build            # TypeScript + Vite production bundle
npm run test             # Vitest unit/integration (MSW + jest-axe)
npm run test:e2e         # Playwright smoke paths
```

From repo root: `make frontend-quality`, `make frontend-tests`, `make frontend-e2e`.

## Size limits (new and migrated code)

| Category | Max effective lines |
| --- | ---: |
| Route/page or module view | 180 |
| Feature component | 220 |
| Hook | 160 |
| API client or store | 220 |
| Type or utility file | 180 |
| Any frontend source file | 400 |

Effective lines exclude blank lines and whole-line `//` comments.
