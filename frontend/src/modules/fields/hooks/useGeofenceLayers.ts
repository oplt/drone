import { useQuery } from "@tanstack/react-query";
import { fieldsKeys } from "../../../app/config/queryKeys";
import { fetchActiveGeofenceRings } from "../api/geofencesApi";

export function useGeofenceLayers() {
  const query = useQuery({
    queryKey: fieldsKeys.geofences(),
    queryFn: fetchActiveGeofenceRings,
    staleTime: 60_000,
  });

  return {
    exclusionZones: query.data ?? [],
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
