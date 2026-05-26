import { useQuery } from "@tanstack/react-query";
import { fieldsKeys } from "../../../app/config/queryKeys";
import { getSessionMarker } from "../../session";
import { fetchFieldLatestTileset } from "../api/mappingApi";

export function useFieldTileset(fieldId: number | null) {
  const token = getSessionMarker();

  const query = useQuery({
    queryKey: fieldsKeys.tileset(fieldId ?? 0),
    queryFn: () => fetchFieldLatestTileset(fieldId!, token),
    enabled: fieldId != null && Boolean(token),
  });

  return {
    tilesetUrl: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
