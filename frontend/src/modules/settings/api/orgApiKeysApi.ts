import { httpRequest } from "../../../shared/api/httpClient";
import { unwrapPage, type PageResponse } from "../../../shared/api/pagination";

export type OrgApiKey = {
  id: number;
  name: string;
  key_prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  revoked: boolean;
  last_used_at: string | null;
};

export type OrgApiKeyCreated = OrgApiKey & {
  raw_key: string;
};

export function listOrgApiKeys(token?: string | null) {
  return httpRequest<PageResponse<OrgApiKey>>("/tasks/api-keys", {
    token,
  }).then(unwrapPage);
}

export function createOrgApiKey(name: string, token?: string | null) {
  return httpRequest<OrgApiKeyCreated>("/tasks/api-keys", {
    method: "POST",
    body: { name, scopes: [] },
    token,
  });
}

export function revokeOrgApiKey(keyId: number, token?: string | null) {
  return httpRequest<void>(`/tasks/api-keys/${keyId}`, {
    method: "DELETE",
    token,
  });
}
