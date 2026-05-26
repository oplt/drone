import type { PreflightSettings } from "../api/preflightApi";
import type { CategoryKey, RowStatus } from "./preflightTypes";

export const DEFAULT_PREFLIGHT_SETTINGS: PreflightSettings = {
  HDOP_MAX: 2.0,
  SAT_MIN: 10,
  HOME_MAX_DIST: 30.0,
  GPS_FIX_TYPE_MIN: 3,
  EKF_THRESHOLD: 0.8,
  COMPASS_HEALTH_REQUIRED: true,
  BATTERY_MIN_V: 0,
  BATTERY_MIN_PERCENT: 20.0,
  HEARTBEAT_MAX_AGE: 3.0,
  MSG_RATE_MIN_HZ: 2.0,
  RTL_MIN_ALT: 15.0,
  MIN_CLEARANCE: 3.0,
  AGL_MIN: 5.0,
  AGL_MAX: 120.0,
  MAX_RANGE_M: 1500.0,
  MAX_WAYPOINTS: 60,
  NFZ_BUFFER_M: 15.0,
  A_LAT_MAX: 3.0,
  BANK_MAX_DEG: 30.0,
  TURN_PENALTY_S: 2.0,
  WP_RADIUS_M: 2.0,
};

export const CATEGORY_LABELS: Record<CategoryKey, string> = {
  SYSTEM_STATUS: "SYSTEM STATUS",
  DRONE_STATUS: "DRONE STATUS",
  MISSION: "MISSION",
};

export const getByPath = (obj: unknown, path: string): unknown => {
  if (!obj) return null;
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return null;
    current = (current as Record<string, unknown>)[part];
  }
  return current ?? null;
};

export const pickFirst = (obj: unknown, paths: string[] = []): unknown => {
  for (const path of paths) {
    const value = getByPath(obj, path);
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return null;
};

export const asNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

export const asBoolean = (value: unknown): boolean | null => {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "yes", "ok", "pass", "1"].includes(normalized)) return true;
    if (["false", "no", "fail", "0"].includes(normalized)) return false;
  }
  return null;
};

export const extractFirstNumber = (text: string | null | undefined): number | null => {
  if (!text) return null;
  const match = text.match(/-?\d+(\.\d+)?/);
  return match ? Number(match[0]) : null;
};

export const toPrettyNumber = (value: number, decimals = 1): string => {
  if (!Number.isFinite(value)) return "--";
  if (Number.isInteger(value)) return `${value}`;
  return value.toFixed(decimals);
};

export const statusToChipColor = (
  status: string,
): "success" | "warning" | "error" | "default" => {
  const s = String(status).toUpperCase();
  if (s === "PASS") return "success";
  if (s === "WARN") return "warning";
  if (s === "FAIL") return "error";
  return "default";
};

export const normalizeStatus = (status?: string | null): RowStatus => {
  const s = String(status || "").toUpperCase();
  if (s === "PASS") return "PASS";
  if (s === "FAIL") return "FAIL";
  if (s === "WARN") return "WARN";
  if (s === "SKIP") return "SKIP";
  return "NOT_RUN";
};

export const statusPriority = (status: RowStatus): number => {
  if (status === "FAIL") return 4;
  if (status === "WARN") return 3;
  if (status === "SKIP") return 2;
  if (status === "PASS") return 1;
  return 0;
};

export const statusDotColor = (status: RowStatus): string => {
  if (status === "PASS") return "#74c145";
  if (status === "FAIL") return "#e35d5d";
  if (status === "WARN") return "#f0b429";
  if (status === "SKIP") return "#90a4ae";
  return "#cfd8dc";
};

export const haversineMeters = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number => {
  const R = 6371000;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) *
      Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

export const missionRangeFromTelemetry = (telemetry: unknown): number | null => {
  const lat = asNumber(pickFirst(telemetry, ["position.lat", "lat"]));
  const lon = asNumber(pickFirst(telemetry, ["position.lon", "lon", "position.lng"]));
  const homeLat = asNumber(pickFirst(telemetry, ["home_lat", "home.lat"]));
  const homeLon = asNumber(pickFirst(telemetry, ["home_lon", "home.lon"]));
  if (
    lat === null ||
    lon === null ||
    homeLat === null ||
    homeLon === null
  ) {
    return null;
  }
  return haversineMeters(homeLat, homeLon, lat, lon);
};
