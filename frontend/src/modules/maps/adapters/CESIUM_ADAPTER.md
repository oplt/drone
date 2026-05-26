# Cesium map adapter boundary

`CesiumMap.tsx` is a temporary monolithic adapter (~1000 effective lines) that owns:

- Cesium viewer lifecycle and terrain/imagery providers
- Field tileset, route polyline, exclusion zones, and drone marker layers
- Terra-style draw interactions delegated from workflow pages
- Camera modes (top, tilted, follow, FPV, orbit)

## Public entry points

| Import | Use when |
| --- | --- |
| `CesiumMapLazy` | **Default** — route-level map viewports (`MissionMapViewport`) |
| `CesiumMap` | Tests or tooling that need synchronous load |

Workflow pages must **not** import `CesiumMap` directly. Use `MissionMapViewport` with `mapEngine="cesium"` or `useCesium`.

## Bundle strategy

`MissionMapViewport` imports `CesiumMapLazy`, which code-splits Cesium/Resium into a separate chunk. Dashboard, auth, fleet, and settings routes do not load Cesium until a map workflow mounts.

## Future decomposition

When splitting `CesiumMap.tsx`, extract in this order:

1. `cesium/viewerSetup.ts` — viewer creation, terrain, base imagery
2. `cesium/layers/` — tileset, routes, geofences, drone entity
3. `cesium/drawing.ts` — pick/draw handlers
4. `cesium/camera.ts` — view modes and follow behavior
5. Thin `CesiumMap.tsx` composing the above (<220 lines)

Each extracted file needs unit tests for pure helpers and a smoke test via `useMapEngine.test.ts` + map route E2E.

## Regression checks

```bash
cd frontend
npm run build
npx vitest run src/modules/maps/tests
```
