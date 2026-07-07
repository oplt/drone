# Oversized map and warehouse modules

Ranked by effective lines, then six-month commit count. Counts were captured before extraction.

| Rank | Module | Effective lines | Commits | First extraction boundary |
| ---: | --- | ---: | ---: | --- |
| 1 | `warehouse/views/Warehouse.tsx` | 1,420 | 18 | API DTO/load mutations into domain hooks; retain page orchestration |
| 2 | `maps/adapters/CesiumMap.tsx` | 1,196 | 5 | camera/ring calculations, then drawing controller hook |
| 3 | `warehouse/components/WarehouseLiveVoxelScene.tsx` | 711 | 8 | render-budget calculations, then focused scene overlays |
| 4 | `warehouse/components/WarehouseCoordinateSetupPanel.tsx` | 707 | 5 | draft parsing and API mapping, then target table/editor sections |
| 5 | `maps/adapters/MapLibreMap.tsx` | 548 | 5 | marker/GeoJSON builders, then drawing controller hook |

## Extraction sequence

1. Cesium camera geometry — extracted and covered by unit tests; adapter reduced below its recorded baseline without changing the baseline.
2. Cesium drawing controller — next isolated review unit.
3. MapLibre marker and GeoJSON builders, then drawing state.
4. Warehouse live-map render planning and overlays.
5. Warehouse coordinate draft/API state.
6. Warehouse page resource hooks, one resource family per review.

Each unit must pass targeted tests and production build before the next unit. File-size baselines change only after a reviewed reduction, never to accept new growth.
