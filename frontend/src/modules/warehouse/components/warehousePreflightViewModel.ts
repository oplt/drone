import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";
import type { WarehouseUiStatus } from "./WarehouseStatusBadge";

export type PreflightCheckView = {
  key: string;
  label: string;
  status: WarehouseUiStatus;
  rawStatus: string;
  detail?: string;
};

export type PreflightGroupView = {
  title: string;
  checks: PreflightCheckView[];
};

const CHECK_LABELS: Record<string, string> = {
  bridge: "Bridge / ROS link",
  vehicle_link: "Drone link",
  telemetry_stream: "Telemetry stream",
  source_transport: "Source transport",
  rgb_depth_imu: "RGB / depth / IMU",
  lidar: "Raw lidar",
  sensors: "Core sensors",
  odometry: "Local odometry",
  localization: "SLAM / localization",
  tf: "TF tree",
  nvblox: "Nvblox",
  stability: "Perception stability",
};

const GROUPS = [
  ["Connectivity", ["bridge", "vehicle_link", "telemetry_stream"]],
  ["Simulation & sensors", ["source_transport", "rgb_depth_imu", "lidar", "sensors"]],
  ["Localization", ["odometry", "localization", "tf"]],
  ["Perception", ["nvblox", "stability"]],
] as const;

export function normalizeWarehouseStatus(value: unknown): WarehouseUiStatus {
  const normalized = String(value ?? "").toLowerCase();
  if (["ok", "pass", "ready", "true", "healthy", "live"].includes(normalized))
    return "ready";
  if (
    ["fail", "failed", "blocked", "false", "missing", "error", "down"].includes(
      normalized,
    )
  ) {
    return "blocked";
  }
  if (["warn", "warning", "stale", "degraded"].includes(normalized))
    return "warning";
  if (["waiting", "warming", "pending", "not_run"].includes(normalized))
    return "waiting";
  if (["running", "refreshing", "starting"].includes(normalized))
    return "running";
  if (["skip", "skipped", "deferred"].includes(normalized)) return "deferred";
  return "unknown";
}

function detailFor(
  key: string,
  preflight: WarehouseGoPreflight | null,
): string | undefined {
  if (!preflight) return undefined;
  const topic = preflight.diagnostics?.topics?.by_category?.[key];
  if (topic?.detail) return topic.detail;
  if (topic?.topic) return topic.topic;
  if (key === "bridge" && preflight.warehouse_bridge_state) {
    return `Bridge ${preflight.warehouse_bridge_state}`;
  }
  if (key === "stability") {
    return `${preflight.perception_stable_for_ms ?? 0}ms stable`;
  }
  if (key === "tf")
    return preflight.tf_ok ? "odom to base_link OK" : "TF missing";
  return undefined;
}

export function buildPreflightGroups(
  preflight: WarehouseGoPreflight | null,
): PreflightGroupView[] {
  const categories = preflight?.categories ?? {};
  return GROUPS.map(([title, keys]) => ({
    title,
    checks: keys.map((key) => {
      const rawStatus = categories[key] ?? "UNKNOWN";
      return {
        key,
        label: CHECK_LABELS[key] ?? key,
        status: normalizeWarehouseStatus(rawStatus),
        rawStatus,
        detail: detailFor(key, preflight),
      };
    }),
  }));
}

export function preflightProgress(preflight: WarehouseGoPreflight | null) {
  const groups = buildPreflightGroups(preflight);
  const checks = groups.flatMap((group) => group.checks);
  const passed = checks.filter((check) => check.status === "ready").length;
  return { passed, total: checks.length, groups };
}

export function strongestPreflightBlocker(
  preflight: WarehouseGoPreflight | null,
  running: boolean,
): string {
  if (running) return "Warehouse preflight refresh in progress";
  return (
    preflight?.primary_blocker ??
    preflight?.blocking_reasons?.[0] ??
    preflight?.blockers?.[0] ??
    preflight?.last_error ??
    (preflight?.ready_to_fly
      ? "All required systems are stable."
      : "Run preflight checks.")
  );
}

export function readinessStatus(
  preflight: WarehouseGoPreflight | null,
  running: boolean,
): WarehouseUiStatus {
  if (running) return "running";
  if (!preflight) return "unknown";
  if (preflight.ready_to_fly) return "ready";
  if (
    preflight.primary_blocker ||
    preflight.blocking_reasons?.length ||
    preflight.blockers?.length
  ) {
    return "blocked";
  }
  return "waiting";
}
