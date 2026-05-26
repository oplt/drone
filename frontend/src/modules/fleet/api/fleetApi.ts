import { httpRequest } from "../../../shared/api/httpClient";
import type { CertItem, DeviceItem } from "../types";

export async function fetchCertifications(token?: string | null): Promise<CertItem[]> {
  const data = await httpRequest<{ certifications: CertItem[] } | CertItem[]>(
    "/tasks/fleet/certifications",
    { token },
  );
  return Array.isArray(data) ? data : data.certifications ?? [];
}

export async function createCertification(
  payload: {
    cert_type: string;
    cert_number: string;
    issued_at: string;
    expires_at: string | null;
  },
  token?: string | null,
): Promise<CertItem> {
  return httpRequest<CertItem>("/tasks/fleet/certifications", {
    method: "POST",
    body: payload,
    token,
  });
}

export async function fetchDevices(token?: string | null): Promise<DeviceItem[]> {
  const data = await httpRequest<{ devices: DeviceItem[] } | DeviceItem[]>(
    "/tasks/fleet/device-readiness",
    { token },
  );
  return Array.isArray(data) ? data : data.devices ?? [];
}

export async function createDevice(
  payload: {
    device_id: string;
    device_name: string;
    status?: string;
    notes: string | null;
  },
  token?: string | null,
): Promise<DeviceItem> {
  return httpRequest<DeviceItem>("/tasks/fleet/device-readiness", {
    method: "POST",
    body: payload,
    token,
  });
}
