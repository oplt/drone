import { useMemo } from "react";
import { deriveTelemetry } from "../lib/deriveTelemetry";

function formatMaybeNumber(v: unknown, digits = 1) {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "--";
}

function formatMaybePercent(v: unknown) {
  return typeof v === "number" && Number.isFinite(v) ? `${Math.round(v)}%` : "--";
}

export function useMissionCommandMetrics(telemetry: any) {
  return useMemo(() => {
    const telemetrySummary = deriveTelemetry(telemetry);

    const batteryCellsRaw =
      telemetry?.battery?.cells ??
      telemetry?.battery?.cell_voltages ??
      telemetry?.battery_cells ??
      telemetry?.cell_voltages ??
      null;
    const batteryCells = Array.isArray(batteryCellsRaw) ? batteryCellsRaw : null;

    const linkRc =
      telemetry?.link?.rc ??
      telemetry?.rc?.quality ??
      telemetry?.rc_quality ??
      telemetry?.rssi ??
      null;
    const linkLte =
      telemetry?.link?.lte ??
      telemetry?.lte?.quality ??
      telemetry?.lte_quality ??
      null;
    const linkTelemetry =
      telemetry?.link?.telemetry ??
      telemetry?.telemetry?.quality ??
      telemetry?.telemetry_quality ??
      null;
    const windSpeed =
      telemetry?.wind?.speed ??
      telemetry?.wind_speed ??
      telemetry?.windSpeed ??
      null;
    const failsafeRaw =
      telemetry?.failsafe?.state ??
      telemetry?.failsafe_state ??
      telemetry?.status?.failsafe ??
      null;

    const batteryCellDisplay = batteryCells?.length
      ? batteryCells.map((v) => `${formatMaybeNumber(Number(v), 2)}V`).join(" / ")
      : "--";

    const linkParts: string[] = [];
    if (linkRc !== null && linkRc !== undefined) {
      linkParts.push(`RC ${formatMaybePercent(Number(linkRc))}`);
    }
    if (linkLte !== null && linkLte !== undefined) {
      linkParts.push(`LTE ${formatMaybePercent(Number(linkLte))}`);
    }
    if (linkTelemetry !== null && linkTelemetry !== undefined) {
      linkParts.push(`TEL ${formatMaybePercent(Number(linkTelemetry))}`);
    }
    const linkQuality = linkParts.length > 0 ? linkParts.join(" • ") : "--";

    const failsafeActive =
      typeof failsafeRaw === "boolean"
        ? failsafeRaw
        : typeof failsafeRaw === "string"
          ? !["none", "ok", "inactive"].includes(failsafeRaw.toLowerCase())
          : false;

    const windDisplay =
      windSpeed === null || windSpeed === undefined
        ? "--"
        : `${formatMaybeNumber(Number(windSpeed), 1)} m/s`;

    return {
      flightStatus: telemetrySummary.flightStatus,
      gpsStrength: telemetrySummary.gpsStrength,
      batteryHealth: telemetrySummary.batteryHealth,
      failsafeState: telemetrySummary.failsafe,
      batteryCellDisplay,
      linkQuality,
      windDisplay,
      failsafeActive,
      heading:
        telemetry?.status?.heading ??
        telemetry?.heading ??
        telemetry?.yaw ??
        null,
      armed: Boolean(telemetry?.armed ?? telemetry?.status?.armed),
    };
  }, [telemetry]);
}
