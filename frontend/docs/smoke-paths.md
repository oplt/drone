# Frontend Smoke Paths

Manual and automated checks for mission-critical flows during architecture migration.
E2E coverage starts minimal in Stage 0 and expands per workflow module.

## Automated (Playwright)

| Path | Spec | What it verifies |
| --- | --- | --- |
| Auth guard | `e2e/smoke/auth-guard.spec.ts` | Unauthenticated `/dashboard` redirects to `/signin` |
| Mission shell | `e2e/smoke/controlled-flight.spec.ts` | Authenticated `/dashboard/controlled` loads mission UI shell |

Run: `cd frontend && npm run test:e2e`

## Manual smoke checklist

Use after changes to routing, session, maps, or mission runtime:

1. **Sign in** — `/signin` accepts credentials; session cookie and marker set.
2. **Dashboard open** — `/dashboard` loads shell, navigation, and home tab.
3. **Mission workflow load** — open Controlled Flight (`/dashboard/controlled`); map/status panels render without console errors.
4. **Field / map interaction** — `/dashboard/field` loads; map viewport and field list respond.
5. **Preflight / launch** — preflight panel reachable; launch blocked when checks fail (do not launch on production without ops approval).
6. **Command actions** — command panel visible on controlled flight; disabled or gated when offline/unauthenticated.
7. **Logout** — session cleared; protected routes redirect to sign-in.

## Environment

- API proxy: Vite dev server proxies `/api`, `/auth`, `/telemetry`, `/ws` to backend (`vite.config.ts`).
- E2E uses mocked auth responses when `E2E_MOCK_AUTH=1` (default in CI) so tests do not require a live backend.
