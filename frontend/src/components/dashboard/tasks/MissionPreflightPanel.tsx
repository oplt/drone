import { useEffect, useMemo, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { getToken } from "../../../auth";
import type { PreflightRunResponse } from "../../../utils/api";

type PreflightSettings = Record<string, number | boolean | string | null | undefined>;
type RowStatus = "PASS" | "FAIL" | "WARN" | "SKIP" | "NOT_RUN";
type RowOperation = "max" | "min" | "required";
type CategoryKey = "SYSTEM_STATUS" | "DRONE_STATUS" | "MISSION";

type PreflightCheck = {
  name: string;
  status: string;
  message?: string | null;
};

type ParameterDefinition = {
  id: string;
  category: CategoryKey;
  label: string;
  settingKey: string;
  op: RowOperation;
  unit?: string;
  decimals?: number;
  checkNames: string[];
  telemetryPaths?: string[];
  deriveActual?: (telemetry: any, check: PreflightCheck | null) => unknown;
};

const DEFAULT_PREFLIGHT_SETTINGS: PreflightSettings = {
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

const CATEGORY_LABELS: Record<CategoryKey, string> = {
  SYSTEM_STATUS: "SYSTEM STATUS",
  DRONE_STATUS: "DRONE STATUS",
  MISSION: "MISSION",
};

const getByPath = (obj: any, path: string): unknown => {
  if (!obj) return null;
  const parts = path.split(".");
  let current = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return null;
    current = (current as Record<string, unknown>)[part];
  }
  return current ?? null;
};

const pickFirst = (obj: any, paths: string[] = []): unknown => {
  for (const path of paths) {
    const value = getByPath(obj, path);
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return null;
};

const asNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const asBoolean = (value: unknown): boolean | null => {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "yes", "ok", "pass", "1"].includes(normalized)) return true;
    if (["false", "no", "fail", "0"].includes(normalized)) return false;
  }
  return null;
};

const extractFirstNumber = (text: string | null | undefined): number | null => {
  if (!text) return null;
  const match = text.match(/-?\d+(\.\d+)?/);
  return match ? Number(match[0]) : null;
};

const toPrettyNumber = (value: number, decimals = 1): string => {
  if (!Number.isFinite(value)) return "--";
  if (Number.isInteger(value)) return `${value}`;
  return value.toFixed(decimals);
};

const statusToChipColor = (
  status: string,
): "success" | "warning" | "error" | "default" => {
  const s = String(status).toUpperCase();
  if (s === "PASS") return "success";
  if (s === "WARN") return "warning";
  if (s === "FAIL") return "error";
  return "default";
};

const normalizeStatus = (status?: string | null): RowStatus => {
  const s = String(status || "").toUpperCase();
  if (s === "PASS") return "PASS";
  if (s === "FAIL") return "FAIL";
  if (s === "WARN") return "WARN";
  if (s === "SKIP") return "SKIP";
  return "NOT_RUN";
};

const statusPriority = (status: RowStatus): number => {
  if (status === "FAIL") return 4;
  if (status === "WARN") return 3;
  if (status === "SKIP") return 2;
  if (status === "PASS") return 1;
  return 0;
};

const statusDotColor = (status: RowStatus): string => {
  if (status === "PASS") return "#74c145";
  if (status === "FAIL") return "#e35d5d";
  if (status === "WARN") return "#f0b429";
  if (status === "SKIP") return "#90a4ae";
  return "#cfd8dc";
};

const haversineMeters = (
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

const missionRangeFromTelemetry = (telemetry: any): number | null => {
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

const PARAMETER_DEFS: ParameterDefinition[] = [
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
        pickFirst(telemetry, ["compass_healthy", "mag_healthy"]),
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
    telemetryPaths: ["heartbeat_age_s", "heartbeat.age_s"],
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

function StatusDot({
  status,
  title,
}: {
  status: RowStatus;
  title: string;
}) {
  return (
    <Tooltip title={title}>
      <Box
        sx={{
          width: 12,
          height: 12,
          borderRadius: "50%",
          bgcolor: statusDotColor(status),
          border: "1px solid",
          borderColor: "rgba(0,0,0,0.18)",
          flexShrink: 0,
        }}
      />
    </Tooltip>
  );
}

export function MissionPreflightPanel({
  apiBase,
  missionType = "route",
  preflightRun,
  telemetry,
  title = "Preflight",
  defaultExpanded = true,
  sx,
}: {
  apiBase: string;
  missionType?: string;
  preflightRun: PreflightRunResponse | null;
  telemetry: any;
  title?: string;
  defaultExpanded?: boolean;
  sx?: any;
}) {
  const [params, setParams] = useState<PreflightSettings>(DEFAULT_PREFLIGHT_SETTINGS);
  const [loadingParams, setLoadingParams] = useState(false);
  const [paramsError, setParamsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadParams = async () => {
      const token = getToken();
      if (!token) return;
      setLoadingParams(true);
      setParamsError(null);
      try {
        const res = await fetch(`${apiBase}/api/settings`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          throw new Error(`Failed to load preflight settings (${res.status})`);
        }
        const data = await res.json();
        if (cancelled) return;
        const preflight =
          data?.preflight && typeof data.preflight === "object" ? data.preflight : {};
        setParams({ ...DEFAULT_PREFLIGHT_SETTINGS, ...preflight });
      } catch (error) {
        if (cancelled) return;
        setParamsError(
          error instanceof Error ? error.message : "Failed to load preflight settings",
        );
      } finally {
        if (!cancelled) setLoadingParams(false);
      }
    };

    loadParams();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const allChecks = useMemo<PreflightCheck[]>(
    () => [
      ...(preflightRun?.report?.base_checks ?? []),
      ...(preflightRun?.report?.mission_checks ?? []),
    ],
    [preflightRun],
  );

  const checkLookup = useMemo(() => {
    const map = new Map<string, PreflightCheck[]>();
    for (const check of allChecks) {
      const key = String(check.name || "").toLowerCase();
      if (!key) continue;
      const list = map.get(key) ?? [];
      list.push(check);
      map.set(key, list);
    }
    return map;
  }, [allChecks]);

  const rowsByCategory = useMemo(() => {
    const normalizedMissionType = String(missionType).toLowerCase();
    const showMissionRows = ["route", "grid", "photogrammetry", "orbit"].includes(
      normalizedMissionType,
    );

    const byCategory: Record<
      CategoryKey,
      Array<{
        id: string;
        label: string;
        defaultValue: string;
        actualValue: string;
        status: RowStatus;
        statusDetail: string;
      }>
    > = {
      SYSTEM_STATUS: [],
      DRONE_STATUS: [],
      MISSION: [],
    };

    for (const def of PARAMETER_DEFS) {
      if (def.category === "MISSION" && !showMissionRows) {
        continue;
      }

      const thresholdRaw = params[def.settingKey];
      const thresholdNum = asNumber(thresholdRaw);
      const thresholdBool = asBoolean(thresholdRaw);

      const matchedChecks = def.checkNames.flatMap((name) => {
        const checks = checkLookup.get(name.toLowerCase());
        return checks ?? [];
      });
      const matchedCheck =
        matchedChecks.length === 0
          ? null
          : [...matchedChecks].sort((a, b) => {
              const aRank = statusPriority(normalizeStatus(a.status));
              const bRank = statusPriority(normalizeStatus(b.status));
              return bRank - aRank;
            })[0];

      let actualRaw: unknown = null;
      if (def.deriveActual) {
        actualRaw = def.deriveActual(telemetry, matchedCheck);
      } else if (def.telemetryPaths && def.telemetryPaths.length > 0) {
        actualRaw = pickFirst(telemetry, def.telemetryPaths);
      }

      const actualNum = asNumber(actualRaw);
      const actualBool = asBoolean(actualRaw);

      let actualValue = "--";
      if (typeof actualRaw === "string" && actualRaw.trim() !== "") {
        actualValue = actualRaw;
      } else if (actualNum !== null) {
        actualValue = `${toPrettyNumber(actualNum, def.decimals ?? 1)}${def.unit ? def.unit : ""}`;
      } else if (actualBool !== null) {
        actualValue = actualBool ? "OK" : "NOT OK";
      }

      let defaultValue = "--";
      if (def.op === "required") {
        defaultValue = thresholdBool ? "Required" : "Optional";
      } else if (thresholdNum !== null) {
        defaultValue = `${def.op === "max" ? "<=" : ">="}${toPrettyNumber(thresholdNum, def.decimals ?? 1)}${def.unit ? def.unit : ""}`;
      } else if (thresholdRaw !== null && thresholdRaw !== undefined && thresholdRaw !== "") {
        defaultValue = String(thresholdRaw);
      }

      let rowStatus: RowStatus = "NOT_RUN";
      let statusDetail = "No preflight result yet";
      if (matchedCheck) {
        rowStatus = normalizeStatus(matchedCheck.status);
        statusDetail = matchedCheck.message || matchedCheck.status || "Preflight check result";
      } else if (actualNum !== null && thresholdNum !== null) {
        rowStatus =
          def.op === "max"
            ? actualNum <= thresholdNum
              ? "PASS"
              : "FAIL"
            : actualNum >= thresholdNum
              ? "PASS"
              : "FAIL";
        statusDetail = "Live telemetry evaluation";
      } else if (def.op === "required" && thresholdBool !== null && actualBool !== null) {
        if (thresholdBool) {
          rowStatus = actualBool ? "PASS" : "FAIL";
        } else {
          rowStatus = "PASS";
        }
        statusDetail = "Live telemetry evaluation";
      } else if (preflightRun) {
        rowStatus = "SKIP";
        statusDetail = "No value available from telemetry/check result";
      }

      byCategory[def.category].push({
        id: def.id,
        label: def.label,
        defaultValue,
        actualValue,
        status: rowStatus,
        statusDetail,
      });
    }

    return byCategory;
  }, [missionType, params, telemetry, checkLookup, preflightRun]);

  const overallStatus = preflightRun?.overall_status ?? "NOT_RUN";
  const summary = preflightRun?.report?.summary;
  const readyToArm =
    preflightRun?.can_start_mission ??
    (overallStatus === "PASS" || overallStatus === "WARN");

  return (
    <Accordion
      disableGutters
      defaultExpanded={defaultExpanded}
      sx={{
        borderRadius: 2,
        border: "1px solid",
        borderColor: "hsla(174, 30%, 40%, 0.25)",
        background: "hsla(0, 0%, 100%, 0.7)",
        "&:before": { display: "none" },
        ...sx,
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreRoundedIcon />}
        sx={{ px: 2, py: 0.25, minHeight: 0 }}
      >
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle1">{title}</Typography>
          <Chip size="small" label={overallStatus} color={statusToChipColor(overallStatus)} />
          {preflightRun?.preflight_run_id && (
            <Chip size="small" label={preflightRun.preflight_run_id} variant="outlined" />
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ px: 2, pb: 2, pt: 0.5 }}>
        <Stack spacing={1.25}>
          {typeof summary?.passed === "number" && (
            <Stack direction="row" spacing={0.8} flexWrap="wrap">
              <Chip size="small" color="success" label={`Pass ${summary.passed}`} />
              <Chip size="small" color="warning" label={`Warn ${summary.warned ?? 0}`} />
              <Chip size="small" color="error" label={`Fail ${summary.failed ?? 0}`} />
            </Stack>
          )}

          {loadingParams && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 0.75 }}>
              <CircularProgress size={18} />
            </Box>
          )}
          {paramsError && <Alert severity="warning">{paramsError}</Alert>}

          {(["SYSTEM_STATUS", "DRONE_STATUS", "MISSION"] as CategoryKey[]).map((categoryKey) => (
            <Box key={categoryKey}>
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 700,
                  letterSpacing: 0.8,
                  fontFamily: "monospace",
                  display: "block",
                  mb: 0.6,
                }}
              >
                {CATEGORY_LABELS[categoryKey]}
              </Typography>
              <TableContainer
                sx={{
                  border: "1px dashed",
                  borderColor: "rgba(35, 70, 58, 0.22)",
                  borderRadius: 1.25,
                  background: "rgba(255,255,255,0.62)",
                }}
              >
                <Table
                  size="small"
                  sx={{
                    "& .MuiTableCell-root": {
                      borderColor: "rgba(35, 70, 58, 0.12)",
                      fontFamily: "monospace",
                      fontSize: "0.72rem",
                      py: 0.55,
                    },
                  }}
                >
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ width: "40%" }}>Parameter</TableCell>
                      <TableCell sx={{ width: "22%" }}>Default</TableCell>
                      <TableCell sx={{ width: "26%" }}>Actual</TableCell>
                      <TableCell align="center" sx={{ width: "12%" }}>
                        Status
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rowsByCategory[categoryKey].map((row) => (
                      <TableRow key={row.id}>
                        <TableCell>{row.label}</TableCell>
                        <TableCell>{row.defaultValue}</TableCell>
                        <TableCell>{row.actualValue}</TableCell>
                        <TableCell align="center">
                          <StatusDot status={row.status} title={`${row.status}: ${row.statusDetail}`} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          ))}

          <Stack direction="row" spacing={1} alignItems="center" sx={{ pt: 0.25 }}>
            <StatusDot
              status={readyToArm ? "PASS" : "FAIL"}
              title={readyToArm ? "Ready to arm" : "Not ready to arm"}
            />
            <Typography variant="caption" sx={{ fontWeight: 700, letterSpacing: 0.5 }}>
              {readyToArm ? "READY TO ARM" : "NOT READY TO ARM"}
            </Typography>
          </Stack>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
