import { getApiBaseUrl } from "../../../app/config/env";
import { ApiError } from "../../../shared/api/apiError";
import { httpRequest, resolveApiUrl } from "../../../shared/api/httpClient";
import type { FieldMappingReadyResponse } from "../types";

export function toAbsoluteAssetUrl(url: string): string {
  if (!url) return url;
  if (/^https?:\/\//i.test(url)) return url;
  const base = getApiBaseUrl();
  if (url.startsWith("/")) return base ? `${base}${url}` : url;
  return resolveApiUrl(url);
}

export async function fetchFieldLatestTileset(
  fieldId: number,
  token?: string | null,
): Promise<string | null> {
  let payload: FieldMappingReadyResponse;
  try {
    payload = await httpRequest<FieldMappingReadyResponse>(
      `/mapping/fields/${fieldId}/latest-ready`,
      { token, suppressErrorLogStatuses: [404] },
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
  const assets = Array.isArray(payload?.assets) ? payload.assets : [];
  const tilesetAsset = assets.find((a) => a?.type === "TILESET_3D");
  const rawUrl = typeof tilesetAsset?.url === "string" ? tilesetAsset.url : "";
  return rawUrl ? toAbsoluteAssetUrl(rawUrl) : null;
}
