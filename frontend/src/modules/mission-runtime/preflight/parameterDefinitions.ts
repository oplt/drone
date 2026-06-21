import type { ParameterDefinition } from "./preflightTypes";
import {
  asBoolean,
  asNumber,
  extractFirstNumber,
  missionRangeFromTelemetry,
  normalizeStatus,
  pickFirst,
} from "./preflightUtils";

export const PARAMETER_DEFS: ParameterDefinition[] = [
  {
    id: "hdop",
    category: "SYSTEM_STATUS",
    label: "HDOP",
    settingKey: "HDOP_MAX",
    op: "max",
    decimals: 2,
    checkNames: ["GPS HDOP"],
    telemetryPaths: ["gps.hdop", "hdop", "gps_hdop"],
  },
  {
    id: "satellites",
    category: "SYSTEM_STATUS",
    label: "Satellites",
    settingKey: "SAT_MIN",
    op: "min",
    checkNames: ["GPS Satellites"],
    telemetryPaths: ["gps.satellites", "satellites_visible", "satellites"],
  },
  {
    id: "gps_fix",
    category: "SYSTEM_STATUS",
    label: "GPS Fix",
    settingKey: "GPS_FIX_TYPE_MIN",
    op: "min",
    checkNames: ["GPS Fix Type"],
    telemetryPaths: ["gps.fix_type", "gps_fix_type"],
  },
  {
    id: "ekf",
    category: "SYSTEM_STATUS",
    label: "EKF",
    settingKey: "EKF_THRESHOLD",
    op: "max",
    decimals: 3,
    checkNames: ["EKF Innovation", "EKF Health"],
    deriveActual: (telemetry, check) => {
      const innovation = asNumber(
        pickFirst(telemetry, [
          "innovation_consistency",
          "ekf.innovation_consistency",
          "ekf_innovation",
        ]),
      );
      if (innovation !== null) return innovation;

      const ekfOk = asBoolean(
        pickFirst(telemetry, ["ekf_ok", "ekf.ok"]),
      );
      if (ekfOk !== null) return ekfOk ? "OK" : "NOT OK";

      return extractFirstNumber(check?.message);
    },
  },
  {
    id: "compass",
    category: "SYSTEM_STATUS",
    label: "Compass",
    settingKey: "COMPASS_HEALTH_REQUIRED",
    op: "required",
    checkNames: ["Compass Health"],
    deriveActual: (telemetry, check) => {
      const healthy = asBoolean(
        pickFirst(telemetry, ["compass.healthy", "compass_healthy", "mag_healthy"]),
      );
      if (healthy !== null) return healthy ? "OK" : "NOT OK";
      if (check?.status) {
        const normalized = normalizeStatus(check.status);
        if (normalized === "PASS") return "OK";
        if (normalized === "FAIL") return "NOT OK";
      }
      return "--";
    },
  },
  {
    id: "battery_percent",
    category: "DRONE_STATUS",
    label: "Battery %",
    settingKey: "BATTERY_MIN_PERCENT",
    op: "min",
    unit: "%",
    checkNames: ["Battery Budget (%)"],
    telemetryPaths: [
      "battery.remaining",
      "battery.percent",
      "battery_remaining",
      "battery.percentage",
    ],
  },
  {
    id: "battery_voltage",
    category: "DRONE_STATUS",
    label: "Battery V",
    settingKey: "BATTERY_MIN_V",
    op: "min",
    unit: "V",
    decimals: 2,
    checkNames: ["Battery Voltage"],
    telemetryPaths: ["battery.voltage", "battery_voltage", "v_batt"],
  },
  {
    id: "heartbeat",
    category: "DRONE_STATUS",
    label: "Heartbeat",
    settingKey: "HEARTBEAT_MAX_AGE",
    op: "max",
    unit: "s",
    decimals: 1,
    checkNames: ["Heartbeat Age"],
    deriveActual: (telemetry, check) => {
      const lastReceived = pickFirst(telemetry, ["heartbeat.last_received"]);
      if (typeof lastReceived === "string" && lastReceived) {
        const ageS = (Date.now() - new Date(lastReceived).getTime()) / 1000;
        return Number.isFinite(ageS) && ageS >= 0 ? ageS : null;
      }
      const ageRaw = asNumber(pickFirst(telemetry, ["heartbeat_age_s", "heartbeat.age_s"]));
      if (ageRaw !== null) return ageRaw;
      return extractFirstNumber(check?.message);
    },
  },
  {
    id: "wind_speed",
    category: "DRONE_STATUS",
    label: "Wind Speed",
    settingKey: "WIND_MAX",
    op: "max",
    unit: " m/s",
    decimals: 1,
    checkNames: ["Wind Speed"],
    deriveActual: (_telemetry, check) => extractFirstNumber(check?.message),
  },
  {
    id: "wind_gust",
    category: "DRONE_STATUS",
    label: "Wind Gust",
    settingKey: "GUST_MAX",
    op: "max",
    unit: " m/s",
    decimals: 1,
    checkNames: ["Wind Gust"],
    deriveActual: (_telemetry, check) => extractFirstNumber(check?.message),
  },
  {
    id: "precipitation",
    category: "DRONE_STATUS",
    label: "Precipitation",
    settingKey: "WEATHER_MAX_PRECIP_MM",
    op: "max",
    unit: " mm",
    decimals: 1,
    checkNames: ["Precipitation"],
    deriveActual: (_telemetry, check) => extractFirstNumber(check?.message),
  },
  {
    id: "visibility",
    category: "DRONE_STATUS",
    label: "Visibility",
    settingKey: "WEATHER_MIN_VISIBILITY_M",
    op: "min",
    unit: " m",
    decimals: 0,
    checkNames: ["Visibility"],
    deriveActual: (_telemetry, check) => extractFirstNumber(check?.message),
  },
  {
    id: "weather_conditions",
    category: "DRONE_STATUS",
    label: "Weather Conditions",
    settingKey: "WEATHER_BLOCKED_CODES",
    op: "required",
    checkNames: ["Weather Conditions", "Weather Availability"],
    deriveActual: (_telemetry, check) => check?.message ?? "--",
  },
  {
    id: "agl_min",
    category: "MISSION",
    label: "AGL Min",
    settingKey: "AGL_MIN",
    op: "min",
    unit: "m",
    checkNames: ["AGL Envelope"],
    telemetryPaths: [
      "position.relative_alt",
      "position.rel_alt_m",
      "status.alt",
      "altitude_terrain_m",
      "agl_m",
    ],
  },
  {
    id: "agl_max",
    category: "MISSION",
    label: "AGL Max",
    settingKey: "AGL_MAX",
    op: "max",
    unit: "m",
    checkNames: ["AGL Envelope"],
    telemetryPaths: [
      "position.relative_alt",
      "position.rel_alt_m",
      "status.alt",
      "altitude_terrain_m",
      "agl_m",
    ],
  },
  {
    id: "mission_range",
    category: "MISSION",
    label: "Range",
    settingKey: "MAX_RANGE_M",
    op: "max",
    unit: "m",
    checkNames: ["Max Range From Home", "Preflight Range"],
    deriveActual: (telemetry, check) => {
      const rangeM = missionRangeFromTelemetry(telemetry);
      if (rangeM !== null) return rangeM;
      return extractFirstNumber(check?.message);
    },
  },
  {
    id: "waypoints",
    category: "MISSION",
    label: "Waypoints",
    settingKey: "MAX_WAYPOINTS",
    op: "max",
    checkNames: ["Waypoint Count"],
    deriveActual: (telemetry, check) => {
      const fromTelem = asNumber(
        pickFirst(telemetry, [
          "mission.waypoints_count",
          "mission.waypoint_count",
          "waypoints_count",
        ]),
      );
      if (fromTelem !== null) return fromTelem;
      return extractFirstNumber(check?.message);
    },
  },
  {
    id: "nfz_buffer",
    category: "MISSION",
    label: "NFZ Buffer",
    settingKey: "NFZ_BUFFER_M",
    op: "min",
    unit: "m",
    checkNames: ["No-Fly Zones"],
    deriveActual: (_telemetry, check) => extractFirstNumber(check?.message),
  },
];
