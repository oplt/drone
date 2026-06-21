import { httpRequest } from "../../../shared/api/httpClient";

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
  return httpRequest<OrgApiKey[]>("/tasks/api-keys", { token });
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
