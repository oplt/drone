import type { Map as MapLibreMapInstance } from "maplibre-gl";
import maplibregl from "maplibre-gl";
import {
  routeLayerId,
  routeSourceId,
  type LonLat,
} from "./maplibreMapTypes";

export function syncMapLibreRoute(
  map: MapLibreMapInstance,
  routeCoordinates: LonLat[],
) {
  if (!map.isStyleLoaded()) return;

  const data =
    routeCoordinates.length >= 2
      ? {
          type: "Feature" as const,
          properties: {},
          geometry: {
            type: "LineString" as const,
            coordinates: routeCoordinates,
          },
        }
      : { type: "FeatureCollection" as const, features: [] };

  const source = map.getSource(routeSourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return;
  }

  map.addSource(routeSourceId, { type: "geojson", data });
  map.addLayer({
    id: routeLayerId,
    type: "line",
    source: routeSourceId,
    paint: {
      "line-color": "#1976d2",
      "line-width": 3,
      "line-opacity": 0.85,
    },
  });
}
