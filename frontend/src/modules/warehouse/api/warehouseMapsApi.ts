import { httpRequest } from "../../../shared/api/httpClient";
import type { CreateWarehouseMapPayload, WarehouseMapOut } from "../types";

export async function listWarehouseMaps(token?: string | null): Promise<WarehouseMapOut[]> {
  return httpRequest<WarehouseMapOut[]>("/warehouse/maps", { token });
}

export async function createWarehouseMap(
  payload: CreateWarehouseMapPayload,
  token?: string | null,
): Promise<WarehouseMapOut> {
  return httpRequest<WarehouseMapOut>("/warehouse/maps", {
    method: "POST",
    body: payload,
    token,
  });
}

export async function fetchSignedTilesetUrl(
  assetId: number,
  token?: string | null,
): Promise<string | null> {
  const data = await httpRequest<{ url?: string }>(
    `/mapping/assets/${assetId}/signed-url?ttl_seconds=3600&path=tileset.json`,
    { token, skipUnauthorizedRedirect: true },
  );
  return typeof data?.url === "string" && data.url.trim() ? data.url : null;
}
