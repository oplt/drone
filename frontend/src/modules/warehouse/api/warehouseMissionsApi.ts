import { httpRequest } from "../../../shared/api/httpClient";
import type {
  WarehouseExplorationProfile,
  WarehouseExplorationStartRequest,
  WarehouseManualMappingCommandResponse,
  WarehouseManualMappingStartRequest,
  WarehouseMissionDefaultsResponse,
  WarehouseMissionLaunchResponse,
  WarehouseScanStartRequest,
  WarehouseScannedMapQualityResponse,
  WarehouseScannedMapResponse,
} from "../types/missions";

export type WarehouseScannedMapCompareResponse = {
  baseline_job_id: number;
  candidate_job_id: number;
  quality_delta?: number | null;
  coverage_delta?: number | null;
  drift_delta_m?: number | null;
};

export async function startWarehouseScan(
  payload: WarehouseScanStartRequest,
  token?: string | null,
): Promise<WarehouseMissionLaunchResponse> {
  return httpRequest<WarehouseMissionLaunchResponse>(
    "/warehouse/missions/start",
    {
      method: "POST",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function startWarehouseExploration(
  payload: WarehouseExplorationStartRequest,
  token?: string | null,
): Promise<WarehouseMissionLaunchResponse> {
  return httpRequest<WarehouseMissionLaunchResponse>(
    "/warehouse/missions/exploration/start",
    {
      method: "POST",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export type WarehouseMappingStackStatus = {
  running: boolean;
  pid: number | null;
  started_at: string | null;
  last_exit_code: number | null;
  last_error: string | null;
  nvblox_running?: boolean;
  phase?: "stopped" | "waiting_sensors" | "running" | string;
};

export async function fetchWarehouseMappingStackStatus(
  token?: string | null,
): Promise<WarehouseMappingStackStatus> {
  return httpRequest<WarehouseMappingStackStatus>(
    "/warehouse/mapping-stack/status",
    {
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function startWarehouseMappingStack(
  token?: string | null,
): Promise<WarehouseMappingStackStatus> {
  return httpRequest<WarehouseMappingStackStatus>(
    "/warehouse/mapping-stack/start",
    {
      method: "POST",
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function stopWarehouseMappingStack(
  token?: string | null,
): Promise<WarehouseMappingStackStatus> {
  return httpRequest<WarehouseMappingStackStatus>(
    "/warehouse/mapping-stack/stop",
    {
      method: "POST",
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function startWarehouseManualMapping(
  payload: WarehouseManualMappingStartRequest,
  token?: string | null,
): Promise<WarehouseManualMappingCommandResponse> {
  return httpRequest<WarehouseManualMappingCommandResponse>(
    "/warehouse/manual-mapping/start",
    {
      method: "POST",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function stopWarehouseManualMapping(
  payload: { flight_id: string; warehouse_map_id?: number | null },
  token?: string | null,
): Promise<WarehouseManualMappingCommandResponse> {
  return httpRequest<WarehouseManualMappingCommandResponse>(
    "/warehouse/manual-mapping/stop",
    {
      method: "POST",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function deleteWarehouseScannedMap(
  jobId: number,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>(`/warehouse/scanned-maps/${jobId}`, {
    method: "DELETE",
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function listWarehouseScannedMaps(
  token?: string | null,
  warehouseMapId?: number | null,
): Promise<WarehouseScannedMapResponse[]> {
  const params = new URLSearchParams();
  if (typeof warehouseMapId === "number" && Number.isFinite(warehouseMapId)) {
    params.set("warehouse_map_id", String(warehouseMapId));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return httpRequest<WarehouseScannedMapResponse[]>(
    `/warehouse/scanned-maps${suffix}`,
    {
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function fetchWarehouseScannedMapQuality(
  jobId: number,
  token?: string | null,
): Promise<WarehouseScannedMapQualityResponse> {
  return httpRequest<WarehouseScannedMapQualityResponse>(
    `/warehouse/scanned-maps/${jobId}/quality`,
    { token, skipUnauthorizedRedirect: true },
  );
}

export async function compareWarehouseScannedMaps(
  baselineJobId: number,
  candidateJobId: number,
  token?: string | null,
): Promise<WarehouseScannedMapCompareResponse> {
  return httpRequest<WarehouseScannedMapCompareResponse>(
    "/warehouse/scanned-maps/compare",
    {
      method: "POST",
      body: {
        baseline_job_id: baselineJobId,
        candidate_job_id: candidateJobId,
      },
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function fetchWarehouseExplorationProfile(
  token?: string | null,
): Promise<WarehouseExplorationProfile> {
  return httpRequest<WarehouseExplorationProfile>(
    "/warehouse/exploration-profile",
    {
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function updateWarehouseExplorationProfile(
  payload: WarehouseExplorationProfile,
  token?: string | null,
): Promise<WarehouseExplorationProfile> {
  return httpRequest<WarehouseExplorationProfile>(
    "/warehouse/exploration-profile",
    {
      method: "PUT",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function fetchWarehouseMissionDefaults(
  token?: string | null,
): Promise<WarehouseMissionDefaultsResponse> {
  return httpRequest<WarehouseMissionDefaultsResponse>(
    "/warehouse/mission-defaults",
    {
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function updateWarehouseMissionDefaults(
  payload: WarehouseMissionDefaultsResponse,
  token?: string | null,
): Promise<WarehouseMissionDefaultsResponse> {
  return httpRequest<WarehouseMissionDefaultsResponse>(
    "/warehouse/mission-defaults",
    {
      method: "PUT",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}
