import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  compareAgricultureFlight,
  duplicateAgriculturePlan,
  listComparableFlights,
  getAgricultureProfile,
  listAgricultureComparisons,
  listAgricultureFieldFlights,
  listAgricultureFieldOverviews,
  listAgricultureTimeline,
  patchAgricultureProfile,
  createAgriculturePlan,
  updateAgriculturePlanGrid,
  evaluateAgriculturePreflight,
  acknowledgeAgriculturePreflight,
  listAgricultureTimelineBookmarks,
  saveAgricultureTimelineBookmark,
  getAgricultureFieldContext,
  createAgricultureField,
  updateAgricultureBoundary,
  addAgricultureZone,
  deleteAgricultureZone,
  listAgricultureFieldPlans,
} from "../../api";
import { agricultureKeys } from "../queryKeys";

export function useAgricultureFieldContext(fieldId: number | null) {
  return useQuery({ queryKey: agricultureKeys.fieldContext(fieldId), queryFn: () => getAgricultureFieldContext(fieldId as number), enabled: fieldId != null });
}

export function useCreateAgricultureField() {
  const client = useQueryClient();
  return useMutation({ mutationFn: createAgricultureField, onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldCatalog() }); } });
}

export function useUpdateAgricultureBoundary() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ fieldId, boundary, reason }: { fieldId: number; boundary: Record<string, unknown>; reason?: string }) => updateAgricultureBoundary(fieldId, { boundary, reason }), onSuccess: (context) => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldContext(context.field_id) }); void client.invalidateQueries({ queryKey: agricultureKeys.fieldCatalog() }); } });
}

export function useAddAgricultureZone() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ fieldId, payload }: { fieldId: number; payload: Parameters<typeof addAgricultureZone>[1] }) => addAgricultureZone(fieldId, payload), onSuccess: (_, variables) => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldContext(variables.fieldId) }); } });
}

export function useDeleteAgricultureZone() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ fieldId, zoneId }: { fieldId: number; zoneId: string }) => deleteAgricultureZone(fieldId, zoneId), onSuccess: (_, variables) => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldContext(variables.fieldId) }); } });
}

export function useCreateAgriculturePlan() {
  return useMutation({ mutationFn: createAgriculturePlan });
}

export function useUpdateAgriculturePlanGrid() {
  return useMutation({ mutationFn: ({ planId, expectedRevision, routeLonlat }: { planId: string; expectedRevision: number; routeLonlat: number[][] }) => updateAgriculturePlanGrid(planId, { expected_revision: expectedRevision, route_lonlat: routeLonlat }) });
}

export function useEvaluateAgriculturePreflight() {
  return useMutation({ mutationFn: ({ planId, notes }: { planId: string; notes?: string }) => evaluateAgriculturePreflight(planId, { notes }) });
}

export function useAcknowledgeAgriculturePreflight() {
  return useMutation({ mutationFn: acknowledgeAgriculturePreflight });
}

export function useAgricultureTimelineBookmarks(flightId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.mediaTimeline(flightId), "bookmarks"], queryFn: () => listAgricultureTimelineBookmarks(flightId as string), enabled: Boolean(flightId) });
}

export function useSaveAgricultureTimelineBookmark() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ flightId, frameLineageId, note }: { flightId: string; frameLineageId: string; note?: string }) => saveAgricultureTimelineBookmark(flightId, { frame_lineage_id: frameLineageId, note }), onSuccess: (bookmark) => { void client.invalidateQueries({ queryKey: [...agricultureKeys.mediaTimeline(bookmark.flight_id ?? null), "bookmarks"] }); } });
}

export function useAgricultureProfile(fieldId: number | null) {
  return useQuery({
    queryKey: agricultureKeys.profile(fieldId),
    queryFn: () => getAgricultureProfile(fieldId as number),
    enabled: fieldId != null,
  });
}

export function usePatchAgricultureProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      fieldId,
      payload,
    }: {
      fieldId: number;
      payload: Partial<import("./types").AgricultureFieldProfile>;
    }) => patchAgricultureProfile(fieldId, payload),
    onSuccess: (profile) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.profile(profile.field_id),
      });
    },
  });
}

export function useAgricultureFieldFlights(fieldId: number | null) {
  return useQuery({
    queryKey: agricultureKeys.fieldFlights(fieldId),
    queryFn: () => listAgricultureFieldFlights(fieldId as number),
    enabled: fieldId != null,
    staleTime: 10_000,
  });
}

export function useAgricultureFields() {
  return useQuery({
    queryKey: agricultureKeys.fieldCatalog(),
    queryFn: listAgricultureFieldOverviews,
    staleTime: 10_000,
  });
}

export function useAgricultureTimeline(fieldId: number | null) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "timeline", fieldId],
    queryFn: () => listAgricultureTimeline(fieldId as number),
    enabled: fieldId != null,
    staleTime: 30_000,
  });
}

export function useAgricultureComparisons(flightId: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "comparisons", flightId],
    queryFn: () => listAgricultureComparisons(flightId as string),
    enabled: Boolean(flightId),
    staleTime: 10_000,
  });
}

export function useCompareAgricultureFlight() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      flightId,
      referenceFlightId,
    }: {
      flightId: string;
      referenceFlightId: string;
    }) =>
      compareAgricultureFlight(flightId, {
        reference_flight_id: referenceFlightId,
      }),
    onSuccess: (result) => {
      void client.invalidateQueries({
        queryKey: [
          ...agricultureKeys.all,
          "comparisons",
          result.current_flight_id,
        ],
      });
    },
  });
}

export function useComparableFlights(flightId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.comparableFlights(flightId),
    queryFn: () => listComparableFlights(flightId as string),
    enabled: Boolean(flightId),
    staleTime: 15_000,
  });
}

export function useDuplicateAgriculturePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => duplicateAgriculturePlan(planId),
    onSuccess: (plan) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.fieldPlans(plan.field_id) });
    },
  });
}

export function useAgricultureFieldPlans(fieldId: number | null) {
  return useQuery({
    queryKey: agricultureKeys.fieldPlans(fieldId),
    queryFn: () => listAgricultureFieldPlans(fieldId as number),
    enabled: fieldId != null,
    staleTime: 15_000,
  });
}
