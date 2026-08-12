import { httpRequest } from "../../../../shared/api/httpClient";
import type {
  AgricultureFlight,
  AgricultureMissionProfile,
  AgriculturePlanPreview,
  AgricultureComparison,
  AgricultureSensorStatus,
  AgricultureUploadSession,
  AgricultureMediaInventory,
  AgricultureMediaTimeline,
  AgricultureTelemetryWindow,
  AgricultureTimelineBookmark,
  AgricultureSensorCalibration,
  AgricultureMediaArtifact,
  AgriculturePlan,
  ComparableFlight,
} from "../../types";

export async function getAgricultureMediaInventory(
  flightId: string,
): Promise<AgricultureMediaInventory> {
  return httpRequest<AgricultureMediaInventory>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/media-inventory`,
  );
}

export async function getAgricultureMediaStatus(mediaId: string): Promise<AgricultureMediaArtifact & { flight_id: string; backup_available: boolean }> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/status`);
}

export async function revokeAgricultureMedia(mediaId: string, reason: string): Promise<unknown> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/revoke`, { method: "POST", body: { reason } });
}

export async function restoreAgricultureMedia(mediaId: string, reason: string): Promise<unknown> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/restore`, { method: "POST", body: { reason } });
}

export async function backupAgricultureMedia(mediaId: string, reason: string): Promise<unknown> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/backup`, { method: "POST", body: { reason } });
}

export async function getAgricultureMediaTimeline(flightId: string): Promise<AgricultureMediaTimeline> {
  return httpRequest<AgricultureMediaTimeline>(`/agriculture/flights/${encodeURIComponent(flightId)}/media-timeline`);
}

export async function getAgricultureTelemetryWindow(flightId: string, timestampUtc: string | null, windowSeconds = 15): Promise<AgricultureTelemetryWindow> {
  const params = new URLSearchParams({ window_seconds: String(windowSeconds) });
  if (timestampUtc) params.set("timestamp_utc", timestampUtc);
  return httpRequest<AgricultureTelemetryWindow>(`/agriculture/flights/${encodeURIComponent(flightId)}/telemetry-window?${params.toString()}`);
}

export async function listAgricultureTimelineBookmarks(flightId: string): Promise<{ flight_id: string; bookmarks: AgricultureTimelineBookmark[] }> {
  return httpRequest(`/agriculture/flights/${encodeURIComponent(flightId)}/timeline/bookmarks`);
}

export async function saveAgricultureTimelineBookmark(flightId: string, payload: { frame_lineage_id: string; note?: string }): Promise<AgricultureTimelineBookmark> {
  return httpRequest(`/agriculture/flights/${encodeURIComponent(flightId)}/timeline/bookmarks`, { method: "POST", body: payload });
}

export async function deleteAgricultureTimelineBookmark(flightId: string, bookmarkId: string): Promise<void> {
  await httpRequest(`/agriculture/flights/${encodeURIComponent(flightId)}/timeline/bookmarks/${encodeURIComponent(bookmarkId)}`, { method: "DELETE" });
}

export async function getAgricultureRuntimeEvents(
  flightId: string,
  afterSequence = 0,
): Promise<{ events: Array<Record<string, unknown>>; next_sequence: number; latest_sequence: number; has_more: boolean; gap_detected: boolean }> {
  return httpRequest<{ events: Array<Record<string, unknown>>; next_sequence: number; latest_sequence: number; has_more: boolean; gap_detected: boolean }>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/runtime/events?after_sequence=${afterSequence}`,
  );
}

export async function sendAgricultureRuntimeCommand(
  flightId: string,
  payload: { command_id: string; command: "pause" | "resume" | "abort" | "rth" | "land"; reason?: string; expected_sequence?: number },
) {
  return httpRequest<{ flight_id: string; command_id: string; command: string; accepted: boolean; state_before: string; state_after: string; message: string; sequence: number; duplicate: boolean }>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/runtime/commands`,
    { method: "POST", body: payload },
  );
}

export async function previewAgricultureFlight(payload: {
  field_id: number | null;
  field_polygon_lonlat: number[][];
  cruise_alt_m: number;
  route_length_m?: number | null;
  profile: AgricultureMissionProfile;
}): Promise<AgriculturePlanPreview> {
  return httpRequest<AgriculturePlanPreview>(
    "/agriculture/flights/plan-preview",
    {
      method: "POST",
      body: payload,
    },
  );
}

export async function getAgricultureFlight(
  flightId: string,
): Promise<AgricultureFlight> {
  return httpRequest<AgricultureFlight>(
    `/agriculture/flights/${encodeURIComponent(flightId)}`,
  );
}

export async function getAgricultureFlightQuality(
  flightId: string,
): Promise<Record<string, unknown>> {
  return httpRequest<Record<string, unknown>>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/quality`,
  );
}

export async function getAgricultureFlightCoverage(
  flightId: string,
): Promise<Record<string, unknown>> {
  return httpRequest<Record<string, unknown>>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/coverage`,
  );
}

export async function getAgricultureSensorStatus(
  flightId: string,
): Promise<AgricultureSensorStatus> {
  return httpRequest<AgricultureSensorStatus>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/sensor-status`,
  );
}

export async function registerAgricultureSensorCalibration(payload: {
  id: string;
  sensor_serial: string;
  sensor_type: "multispectral" | "thermal" | "weather" | "humidity" | "soil_moisture" | "irrigation";
  version: string;
  calibration_kind: string;
  calibration_data?: Record<string, unknown>;
  checksum: string;
  valid_from?: string | null;
  valid_until?: string | null;
}): Promise<AgricultureSensorCalibration> {
  return httpRequest<AgricultureSensorCalibration>("/agriculture/sensor-calibrations", { method: "POST", body: payload });
}

export async function initiateAgricultureUpload(
  flightId: string,
  payload: {
    source_kind:
      | "rgb_video"
      | "rgb_stills"
      | "multispectral"
      | "multispectral_band"
      | "thermal"
      | "orthomosaic";
    filename?: string;
    content_type?: string;
    total_bytes: number;
    checksum: string;
    metadata?: Record<string, unknown>;
  },
): Promise<AgricultureUploadSession> {
  return httpRequest<AgricultureUploadSession>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/uploads`,
    { method: "POST", body: payload },
  );
}

export async function completeAgricultureUpload(
  flightId: string,
  uploadId: string,
): Promise<{
  id: string;
  upload_id: string;
  status: string;
  signed_url?: string;
}> {
  return httpRequest(
    `/agriculture/flights/${encodeURIComponent(flightId)}/uploads/${encodeURIComponent(uploadId)}/complete`,
    { method: "POST" },
  );
}

export async function retryAgricultureUpload(flightId: string, uploadId: string) {
  return httpRequest<{ id: string; status: string; upload_offset: number; total_bytes: number; chunk_bytes?: number; expires_at?: string; retryable: boolean }>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/uploads/${encodeURIComponent(uploadId)}/retry`,
    { method: "POST" },
  );
}

export async function reconcileAgricultureMedia(flightId: string) {
  return httpRequest<AgricultureMediaInventory>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/media-inventory/reconcile`,
    { method: "POST" },
  );
}

export async function compareAgricultureFlight(
  flightId: string,
  payload: { reference_flight_id?: string | null; min_quality_score?: number },
): Promise<AgricultureComparison> {
  return httpRequest<AgricultureComparison>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/compare`,
    { method: "POST", body: payload },
  );
}

export async function listComparableFlights(flightId: string): Promise<ComparableFlight[]> {
  return httpRequest(`/agriculture/flights/${encodeURIComponent(flightId)}/comparable-flights`);
}

export async function duplicateAgriculturePlan(planId: string): Promise<AgriculturePlan> {
  return httpRequest(`/agriculture/flights/plans/${encodeURIComponent(planId)}/duplicate`, { method: "POST" });
}

export async function startAgricultureFlight(
  payload: Record<string, unknown>,
): Promise<{
  flight_id: string;
  status: string;
  mission_name: string;
  mission_type: string;
  waypoints_count: number;
}> {
  return httpRequest("/agriculture/flights/start", {
    method: "POST",
    body: payload,
  });
}

export async function ingestAgricultureTelemetry(
  flightId: string,
  idempotencyKey: string,
  payload: Record<string, unknown>,
): Promise<{
  inserted: number;
  duplicates: number;
  rejected: number;
  gap_count: number;
}> {
  return httpRequest(
    `/agriculture/flights/${encodeURIComponent(flightId)}/telemetry`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: payload,
    },
  );
}
