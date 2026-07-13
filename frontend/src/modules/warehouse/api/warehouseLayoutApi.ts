import { httpRequest } from "../../../shared/api/httpClient";
import { unwrapPage, type PageResponse } from "../../../shared/api/pagination";

export type LayoutKind = "aisles" | "racks" | "shelves" | "bins" | "zones";

export type LayoutEntity = {
  id: number;
  parent_id?: number;
  code?: string;
  level?: number;
  kind?: string;
  geometry: Record<string, unknown>;
  min_z_m?: number | null;
  max_z_m?: number | null;
  active?: boolean;
};

export type LayoutVersion = {
  id: number;
  version: number;
  revision: number;
  status: "draft" | "locked" | "superseded";
  source: string;
};

export type LayoutDocument = Record<LayoutKind, LayoutEntity[]>;

export type LayoutIssue = {
  code: string;
  message: string;
  path: string;
  severity: "error" | "warning";
};

export type LayoutCandidate = {
  id: number;
  identity_key: string;
  confidence: number;
  status: "provisional" | "needs_review" | "accepted" | "rejected";
  displacement_m: number | null;
};

const base = (mapId: number) => `/warehouse/maps/${mapId}/layout-versions`;

export const listLayoutVersions = (mapId: number, token?: string | null) =>
  httpRequest<PageResponse<LayoutVersion>>(base(mapId), { token }).then(
    unwrapPage,
  );

export const createLayoutVersion = (mapId: number, token?: string | null) =>
  httpRequest<LayoutVersion>(base(mapId), {
    method: "POST",
    body: { source: "operator_ui" },
    token,
  });

export async function loadLayoutDocument(
  mapId: number,
  version: number,
  token?: string | null,
): Promise<LayoutDocument> {
  const kinds: LayoutKind[] = ["aisles", "racks", "shelves", "bins", "zones"];
  const pages = await Promise.all(
    kinds.map((kind) =>
      httpRequest<{ revision: number; items: LayoutEntity[] }>(
        `${base(mapId)}/${version}/${kind}`,
        { token },
      ),
    ),
  );
  return Object.fromEntries(
    kinds.map((kind, index) => [kind, pages[index].items]),
  ) as LayoutDocument;
}

async function checksum(value: object): Promise<string> {
  const stable = (item: unknown): string => {
    if (Array.isArray(item)) return `[${item.map(stable).join(",")}]`;
    if (item && typeof item === "object") {
      return `{${Object.entries(item as Record<string, unknown>)
        .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
        .map(([key, child]) => `${JSON.stringify(key)}:${stable(child)}`)
        .join(",")}}`;
    }
    return JSON.stringify(item);
  };
  const encoded = new TextEncoder().encode(stable(value));
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function previewLayoutImport(
  mapId: number,
  layout: LayoutVersion,
  entities: LayoutDocument,
  token?: string | null,
): Promise<{ revision: number; issues: LayoutIssue[] }> {
  const content = {
    schema: "warehouse-layout/v1",
    warehouse_map_id: mapId,
    layout_version: layout.version,
    revision: layout.revision,
    entities,
  };
  return httpRequest<{ revision: number; issues: LayoutIssue[] }>(
    `${base(mapId)}/${layout.version}/import?dry_run=true`,
    {
      method: "POST",
      body: { ...content, checksum_sha256: await checksum(content) },
      headers: { "If-Match": `"${layout.revision}"` },
      token,
    },
  );
}

export async function saveLayoutDocument(
  mapId: number,
  layout: LayoutVersion,
  entities: LayoutDocument,
  token?: string | null,
): Promise<number> {
  const content = {
    schema: "warehouse-layout/v1",
    warehouse_map_id: mapId,
    layout_version: layout.version,
    revision: layout.revision,
    entities,
  };
  const result = await httpRequest<{ revision: number }>(
    `${base(mapId)}/${layout.version}/import?dry_run=false`,
    {
      method: "POST",
      body: { ...content, checksum_sha256: await checksum(content) },
      headers: { "If-Match": `"${layout.revision}"` },
      token,
    },
  );
  return result.revision;
}

export const validateLayout = (
  mapId: number,
  version: number,
  token?: string | null,
) =>
  httpRequest<{ valid: boolean; revision: number; issues: LayoutIssue[] }>(
    `${base(mapId)}/${version}/validate`,
    { method: "POST", token },
  );

export const reviewLayoutDisplacements = (
  mapId: number,
  version: number,
  token?: string | null,
) =>
  httpRequest<{ items: LayoutCandidate[]; needs_review: number }>(
    `${base(mapId)}/${version}/displacement-review`,
    { method: "POST", token },
  );

export const decideLayoutCandidate = (
  mapId: number,
  candidateId: number,
  status: "accepted" | "rejected",
  token?: string | null,
) =>
  httpRequest<{ item: LayoutCandidate }>(
    `/warehouse/maps/${mapId}/layout-candidates/${candidateId}`,
    {
      method: "PATCH",
      body: { status },
      headers: { "If-Match": `"${candidateId}"` },
      token,
    },
  );
