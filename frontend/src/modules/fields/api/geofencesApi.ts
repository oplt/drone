import { httpRequest } from "../../../shared/api/httpClient";
import type { LonLat } from "../types";
import { stripClosedRing } from "../utils/fieldGeometry";

export async function fetchActiveGeofenceRings(): Promise<LonLat[][]> {
  const geofences = await httpRequest<Array<{ id?: number }>>(
    "/geofences?active=true&limit=200",
  );

  const zones: LonLat[][] = [];
  await Promise.all(
    (geofences ?? []).map(async (g) => {
      const id = g?.id;
      if (typeof id !== "number") return;
      const feature = await httpRequest<{ geometry?: { coordinates?: LonLat[][] } }>(
        `/geofences/${id}/geojson`,
      );
      const ring = feature?.geometry?.coordinates?.[0];
      if (Array.isArray(ring) && ring.length >= 4) {
        zones.push(stripClosedRing(ring));
      }
    }),
  );
  return zones;
}
