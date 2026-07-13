import { ApiError } from "../../shared/api/apiError";
import type {
  MissionLifecycleState,
  PreflightRunResponse,
} from "../mission-runtime";
import type { WarehouseFlightReadiness } from "./api/warehouseFlightApi";
import type { WarehouseMappingRuntimeStatus } from "./components/WarehouseMappingHealthPanel";

export type CreateMapForm = {
  name: string;
  width_m: string;
  length_m: string;
};

export type SensorRigForm = {
  name: string;
  camera_model: string;
  stereo_baseline_m: string;
  intrinsics_url: string;
  extrinsics_url: string;
  firmware_version: string;
};

export const WAREHOUSE_SENSOR_TOPIC_LABELS: Record<string, string> = {
  visual_slam_odom: "Local odometry",
  local_odometry: "Local odometry",
  depth: "Depth camera",
  rgb_image: "RGB camera",
  imu: "IMU",
  raw_lidar: "LiDAR",
};

export const formatWarehouseSensorKeys = (keys: string[]): string =>
  [
    ...new Set(keys.map((key) => WAREHOUSE_SENSOR_TOPIC_LABELS[key] ?? key)),
  ].join(", ");

export type WarehouseStartErrorBody = {
  detail?: {
    message?: string;
    user_message?: string;
    failure_code?: string;
    preflight?: PreflightRunResponse;
    readiness?: Record<string, unknown>;
    missing_required_topics?: string[];
    missing_topics?: string[];
    unhealthy_topics?: string[];
    missing_nvblox_topics?: string[];
    suggested_actions?: string[];
    blocking_reasons?: string[];
  };
  error?: {
    message?: string;
    details?: {
      message?: string;
      user_message?: string;
      failure_code?: string;
      preflight?: PreflightRunResponse;
      readiness?: Record<string, unknown>;
      missing_required_topics?: string[];
      missing_topics?: string[];
      unhealthy_topics?: string[];
      missing_nvblox_topics?: string[];
      suggested_actions?: string[];
      blocking_reasons?: string[];
    };
  };
};

export type WarehouseMissionStatus = {
  flight_id?: string;
  mission_name?: string;
  telemetry?: {
    running?: boolean;
    active_connections?: number;
    has_position_data?: boolean;
    position?: {
      lat?: number;
      lon?: number;
      alt?: number;
    };
  };
  orchestrator?: {
    drone_connected?: boolean;
  };
  mission_lifecycle?: {
    flight_id?: string | null;
    state?: MissionLifecycleState;
    mission_name?: string;
    mission_type?: string;
    updated_at?: number;
    last_error?: string | null;
  } | null;
  command_capabilities?: {
    pause?: boolean;
    resume?: boolean;
    abort?: boolean;
  } | null;
  warehouse_mapping?: WarehouseMappingRuntimeStatus | null;
};

export const COMPACT_FIELD_SX = {
  minWidth: 0,
  "& .MuiFilledInput-root": {
    paddingTop: 0,
    paddingBottom: 0,
    backgroundColor: "action.hover",
    "&:hover": { backgroundColor: "action.selected" },
    "&.Mui-focused": { backgroundColor: "action.selected" },
  },
  "& .MuiFilledInput-input": {
    px: 0.75,
    py: 0.85,
    pt: 1.1,
    MozAppearance: "textfield",
    "&::-webkit-outer-spin-button, &::-webkit-inner-spin-button": {
      WebkitAppearance: "none",
      margin: 0,
    },
  },
  "& .MuiSelect-select": { py: 0.85, pt: 1.1 },
  "& .MuiInputAdornment-root": { ml: 0, mr: 0.25 },
  "& .MuiInputAdornment-root .MuiTypography-root": { fontSize: "0.7rem" },
  "& .MuiInputLabel-root": { fontSize: "0.75rem" },
} as const;

export const SENSOR_RIG_CREATE_FIELDS = [
  {
    key: "name" as const,
    label: "Name",
    type: "text" as const,
    adornment: null,
  },
  {
    key: "camera_model" as const,
    label: "Camera",
    type: "text" as const,
    adornment: null,
  },
  {
    key: "stereo_baseline_m" as const,
    label: "Baseline",
    type: "number" as const,
    adornment: "m",
  },
  {
    key: "intrinsics_url" as const,
    label: "Intrinsics",
    type: "text" as const,
    adornment: null,
  },
  {
    key: "extrinsics_url" as const,
    label: "Extrinsics",
    type: "text" as const,
    adornment: null,
  },
  {
    key: "firmware_version" as const,
    label: "Firmware",
    type: "text" as const,
    adornment: null,
  },
] as const;

export const toMessage = (error: unknown): string =>
  error instanceof Error ? error.message : "Request failed";

export const getWarehouseStartPreflight = (
  error: unknown,
): PreflightRunResponse | null => {
  const body = (error as { body?: unknown } | null)?.body as
    | WarehouseStartErrorBody
    | undefined;
  return body?.detail?.preflight ?? body?.error?.details?.preflight ?? null;
};

export const getWarehouseStartReadiness = (
  error: unknown,
): WarehouseFlightReadiness | null => {
  const body = (error as { body?: unknown } | null)?.body as
    | WarehouseStartErrorBody
    | undefined;
  const readiness = body?.detail?.readiness ?? body?.error?.details?.readiness;
  if (!readiness || typeof readiness !== "object") {
    return null;
  }
  return readiness as WarehouseFlightReadiness;
};

export const getWarehouseStartMessage = (error: unknown): string => {
  const body = (error as { body?: unknown } | null)?.body as
    | WarehouseStartErrorBody
    | undefined;
  const detail = body?.detail ?? body?.error?.details;
  if (detail && typeof detail === "object") {
    const parts = [
      (typeof detail.user_message === "string" && detail.user_message) ||
        (typeof detail.message === "string" && detail.message) ||
        "",
    ].filter(Boolean);
    const readinessRecord = detail.readiness;
    const missing = [
      ...new Set([
        ...(detail.missing_required_topics ?? []),
        ...(detail.missing_topics ?? []),
        ...(Array.isArray(readinessRecord?.missing_required_topics)
          ? (readinessRecord.missing_required_topics as string[])
          : []),
      ]),
    ];
    const unhealthy = [
      ...new Set([
        ...(detail.unhealthy_topics ?? []),
        ...(Array.isArray(readinessRecord?.unhealthy_topics)
          ? (readinessRecord.unhealthy_topics as string[])
          : []),
      ]),
    ];
    if (missing.length > 0) {
      parts.push(`Not ready: ${formatWarehouseSensorKeys(missing)}`);
    }
    if (unhealthy.length > 0) {
      parts.push(`Unhealthy: ${formatWarehouseSensorKeys(unhealthy)}`);
    }
    const nvbloxMissing = detail.missing_nvblox_topics ?? [];
    if (nvbloxMissing.length > 0) {
      parts.push(`Nvblox outputs: ${nvbloxMissing.join(", ")}`);
    }
    const actions = detail.suggested_actions ?? [];
    if (actions.length > 0) {
      parts.push(actions[0]);
    }
    const blockingReasons = Array.isArray(detail.blocking_reasons)
      ? (detail.blocking_reasons as string[])
      : [];
    if (blockingReasons.length > 0) {
      parts.push(`Blocked: ${blockingReasons.join("; ")}`);
    }
    const readinessPayload =
      getWarehouseStartReadiness(error) ??
      (detail?.readiness && typeof detail.readiness === "object"
        ? (detail.readiness as WarehouseFlightReadiness)
        : null);
    const blocking = readinessPayload?.blocking_reasons;
    if (blocking && blocking.length > 0) {
      parts.push(`Blocked: ${blocking.join("; ")}`);
    }
    return parts.join(" — ");
  }
  if (body?.error?.message) {
    return body.error.message;
  }
  if (error instanceof ApiError && error.detail) {
    return error.detail;
  }
  return toMessage(error);
};
