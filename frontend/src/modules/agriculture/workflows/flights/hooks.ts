import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  completeAgricultureUpload,
  getAgricultureFlight,
  getAgricultureFlightCoverage,
  getAgricultureFlightQuality,
  getAgricultureSensorStatus,
  initiateAgricultureUpload,
  uploadAgricultureChunk,
  getAgricultureMediaInventory,
  getAgricultureRuntimeEvents,
  sendAgricultureRuntimeCommand,
  getAgricultureMediaTimeline,
  getAgricultureTelemetryWindow,
  reconcileAgricultureMedia,
  revokeAgricultureMedia,
  restoreAgricultureMedia,
  backupAgricultureMedia,
  registerAgricultureSensorCalibration,
} from "../../api";
import { agricultureInvalidationKeys, agricultureKeys, agriculturePollInterval } from "../queryKeys";

export function useRevokeAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ mediaId, reason }: { mediaId: string; reason: string }) => revokeAgricultureMedia(mediaId, reason), onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureInvalidationKeys.mediaInventories() }); } });
}

export function useRestoreAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ mediaId, reason }: { mediaId: string; reason: string }) => restoreAgricultureMedia(mediaId, reason), onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureInvalidationKeys.mediaInventories() }); } });
}

export function useBackupAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ mediaId, reason }: { mediaId: string; reason: string }) => backupAgricultureMedia(mediaId, reason), onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureInvalidationKeys.mediaInventories() }); } });
}

export function useAgricultureMediaInventory(flightId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.mediaInventory(flightId),
    queryFn: () => getAgricultureMediaInventory(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useReconcileAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: reconcileAgricultureMedia,
    onSuccess: (inventory) => {
      void client.setQueryData(agricultureKeys.mediaInventory(inventory.flight_id), inventory);
    },
  });
}

export function useAgricultureMediaTimeline(flightId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.mediaTimeline(flightId),
    queryFn: () => getAgricultureMediaTimeline(flightId as string),
    enabled: Boolean(flightId),
    staleTime: 15_000,
  });
}

export function useAgricultureTelemetryWindow(flightId: string | null, timestampUtc: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.mediaTimeline(flightId), "telemetry-window", timestampUtc],
    queryFn: () => getAgricultureTelemetryWindow(flightId as string, timestampUtc),
    enabled: Boolean(flightId && timestampUtc),
    staleTime: 10_000,
  });
}

export function useAgricultureRuntimeEvents(
  flightId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: agricultureKeys.runtimeEvents(flightId),
    queryFn: () => getAgricultureRuntimeEvents(flightId as string),
    enabled: Boolean(flightId) && enabled,
    refetchInterval: () => agriculturePollInterval(3000),
  });
}

export function useAgricultureRuntimeCommand() {
  return useMutation({ mutationFn: ({ flightId, command, reason, expectedSequence }: { flightId: string; command: "pause" | "resume" | "abort" | "rth" | "land"; reason?: string; expectedSequence?: number }) => sendAgricultureRuntimeCommand(flightId, { command_id: `${flightId}-${command}-${crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`}`.slice(0, 120), command, reason, expected_sequence: expectedSequence }) });
}

export function useAgricultureSensorStatus(
  flightId: string | null,
  active = false,
) {
  return useQuery({
    queryKey: agricultureKeys.sensors(flightId),
    queryFn: () => getAgricultureSensorStatus(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: () => agriculturePollInterval(5000, active),
    staleTime: 5000,
  });
}

export function useRegisterAgricultureSensorCalibration() {
  const client = useQueryClient();
  return useMutation({ mutationFn: registerAgricultureSensorCalibration, onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureKeys.sensors(null) }); } });
}

export function useInitiateAgricultureUpload() {
  return useMutation({
    mutationFn: ({
      flightId,
      payload,
    }: {
      flightId: string;
      payload: Parameters<typeof initiateAgricultureUpload>[1];
    }) => initiateAgricultureUpload(flightId, payload),
  });
}

export function useUploadAgricultureChunk() {
  return useMutation({
    mutationFn: ({
      session,
      chunk,
      signal,
    }: {
      session: Parameters<typeof uploadAgricultureChunk>[0];
      chunk: Blob;
      signal?: AbortSignal;
    }) => uploadAgricultureChunk(session, chunk, signal),
  });
}

export function useCompleteAgricultureUpload() {
  return useMutation({
    mutationFn: ({
      flightId,
      uploadId,
    }: {
      flightId: string;
      uploadId: string;
    }) => completeAgricultureUpload(flightId, uploadId),
  });
}

export function useAgricultureFlight(flightId: string | null, active = false) {
  return useQuery({
    queryKey: agricultureKeys.flight(flightId),
    queryFn: () => getAgricultureFlight(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: () => agriculturePollInterval(3000, active),
  });
}

export function useAgricultureFlightQuality(
  flightId: string | null,
  active = false,
) {
  return useQuery({
    queryKey: agricultureKeys.quality(flightId),
    queryFn: () => getAgricultureFlightQuality(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: () => agriculturePollInterval(3000, active),
  });
}

export function useAgricultureFlightCoverage(
  flightId: string | null,
  active = false,
) {
  return useQuery({
    queryKey: agricultureKeys.coverage(flightId),
    queryFn: () => getAgricultureFlightCoverage(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: () => agriculturePollInterval(3000, active),
  });
}
