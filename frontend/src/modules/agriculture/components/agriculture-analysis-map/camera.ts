import type { Position } from "geojson";
import maplibregl, { type Map as MapLibreMap } from "maplibre-gl";

export function fitAgricultureMap(
  map: MapLibreMap,
  coordinates: Position[],
) {
  if (!coordinates.length) return;
  if (coordinates.length === 1) {
    map.easeTo({ center: coordinates[0] as [number, number], zoom: 16 });
    return;
  }
  const bounds = coordinates.reduce(
    (current, coordinate) => current.extend(coordinate as [number, number]),
    new maplibregl.LngLatBounds(
      coordinates[0] as [number, number],
      coordinates[0] as [number, number],
    ),
  );
  map.fitBounds(bounds, { padding: 44, maxZoom: 17, duration: 0 });
}
