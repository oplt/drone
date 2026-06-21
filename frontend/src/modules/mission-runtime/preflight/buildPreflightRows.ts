import type { PreflightSettings } from "../api/preflightApi";
import type { PreflightRunResponse, TelemetrySnapshot } from "../types";
import { PARAMETER_DEFS } from "./parameterDefinitions";
import type {
  CategoryKey,
  PreflightCheck,
  PreflightRowsByCategory,
  RowStatus,
} from "./preflightTypes";
import {
  asBoolean,
  asNumber,
  normalizeStatus,
  pickFirst,
  statusPriority,
  toPrettyNumber,
} from "./preflightUtils";

function buildCheckLookup(allChecks: PreflightCheck[]): Map<string, PreflightCheck[]> {
  const map = new Map<string, PreflightCheck[]>();
  for (const check of allChecks) {
    const key = String(check.name || "").toLowerCase();
    if (!key) continue;
    const list = map.get(key) ?? [];
    list.push(check);
    map.set(key, list);
  }
  return map;
}

export function buildPreflightRows({
  missionType,
  params,
  telemetry,
  preflightRun,
  droneConnected,
}: {
  missionType: string;
  params: PreflightSettings;
  telemetry: TelemetrySnapshot | null;
  preflightRun: PreflightRunResponse | null;
  /** When false, ignore stale websocket telemetry for rows without a backend check result. */
  droneConnected?: boolean;
}): PreflightRowsByCategory {
  const trustLiveTelemetry = droneConnected !== false;
  const normalizedMissionType = String(missionType).toLowerCase();
  const showMissionRows = [
    "route",
    "grid",
    "photogrammetry",
    "orbit",
    "perimeter_patrol",
    "private_patrol",
  ].includes(normalizedMissionType);

  const allChecks: PreflightCheck[] = [
    ...(preflightRun?.report?.base_checks ?? []),
    ...(preflightRun?.report?.mission_checks ?? []),
  ];
  const checkLookup = buildCheckLookup(allChecks);

  const byCategory: PreflightRowsByCategory = {
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
    } else if (trustLiveTelemetry && actualNum !== null && thresholdNum !== null) {
      rowStatus =
        def.op === "max"
          ? actualNum <= thresholdNum
            ? "PASS"
            : "FAIL"
          : actualNum >= thresholdNum
            ? "PASS"
            : "FAIL";
      statusDetail = "Live telemetry evaluation";
    } else if (
      trustLiveTelemetry &&
      def.op === "required" &&
      thresholdBool !== null &&
      actualBool !== null
    ) {
      if (thresholdBool) {
        rowStatus = actualBool ? "PASS" : "FAIL";
      } else {
        rowStatus = "PASS";
      }
      statusDetail = "Live telemetry evaluation";
    } else if (!trustLiveTelemetry && !matchedCheck) {
      rowStatus = "NOT_RUN";
      statusDetail = "Drone not connected; waiting for live telemetry";
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
}

export const PREFLIGHT_CATEGORIES: CategoryKey[] = [
  "SYSTEM_STATUS",
  "DRONE_STATUS",
  "MISSION",
];
