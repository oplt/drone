import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { httpRequest } from "../../../shared/api/httpClient";

export type AgricultureInterventionZone = {
  id: string;
  org_id: number | null;
  field_id: number;
  flight_id: string;
  run_id: string;
  name: string;
  category: string;
  geometry_geojson: Record<string, unknown>;
  area_m2: number;
  source_observation_ids: string[];
  evidence_ids: string[];
  model_versions: string[];
  status: "proposed" | "approved" | "rejected";
  revision: number;
  created_by_user_id: number | null;
  reviewed_by_user_id: number | null;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AgricultureInterventionZoneAudit = {
  id: string;
  actor_user_id: number | null;
  action: string;
  from_status: string | null;
  to_status: string | null;
  reason: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

const zoneKeys = {
  list: (runId: string | null) => ["agriculture", "intervention-zones", runId] as const,
  audit: (zoneId: string | null) => ["agriculture", "intervention-zone-audit", zoneId] as const,
};

export function useAgricultureInterventionZones(runId: string | null) {
  return useQuery({
    queryKey: zoneKeys.list(runId),
    queryFn: () => httpRequest<AgricultureInterventionZone[]>(`/agriculture/analysis-runs/${encodeURIComponent(runId as string)}/intervention-zones`),
    enabled: Boolean(runId),
  });
}

export function useAgricultureInterventionZoneAudit(zoneId: string | null) {
  return useQuery({
    queryKey: zoneKeys.audit(zoneId),
    queryFn: () => httpRequest<AgricultureInterventionZoneAudit[]>(`/agriculture/intervention-zones/${encodeURIComponent(zoneId as string)}/audit`),
    enabled: Boolean(zoneId),
  });
}

export function useCreateAgricultureInterventionZone() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: { name: string; category: string; source_observation_ids: string[] } }) =>
      httpRequest<AgricultureInterventionZone>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/intervention-zones`, { method: "POST", body: payload }),
    onSuccess: (zone) => void client.invalidateQueries({ queryKey: zoneKeys.list(zone.run_id) }),
  });
}

export function useUpdateAgricultureInterventionZone() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ zone, payload }: { zone: AgricultureInterventionZone; payload: { expected_revision: number; name: string; category: string; geometry_geojson: Record<string, unknown> } }) =>
      httpRequest<AgricultureInterventionZone>(`/agriculture/intervention-zones/${encodeURIComponent(zone.id)}`, { method: "PUT", body: payload }),
    onSuccess: (zone) => {
      void client.invalidateQueries({ queryKey: zoneKeys.list(zone.run_id) });
      void client.invalidateQueries({ queryKey: zoneKeys.audit(zone.id) });
    },
  });
}

export function useReviewAgricultureInterventionZone() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ zone, status, note }: { zone: AgricultureInterventionZone; status: "approved" | "rejected"; note: string }) =>
      httpRequest<AgricultureInterventionZone>(`/agriculture/intervention-zones/${encodeURIComponent(zone.id)}/approval`, { method: "POST", body: { status, note, expected_revision: zone.revision } }),
    onSuccess: (zone) => {
      void client.invalidateQueries({ queryKey: zoneKeys.list(zone.run_id) });
      void client.invalidateQueries({ queryKey: zoneKeys.audit(zone.id) });
    },
  });
}
