import { useMemo } from "react";
import { deriveTelemetry } from "../utils/deriveTelemetry";

function formatMaybeNumber(v: unknown, digits = 1) {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "--";
}

function formatMaybePercent(v: unknown) {
  return typeof v === "number" && Number.isFinite(v) ? `${Math.round(v)}%` : "--";
}

export function useMissionCommandMetrics(telemetry: unknown) {
  return useMemo(() => {
    const telemetrySummary = deriveTelemetry(telemetry);
    const t = (telemetry ?? {}) as Record<string, unknown>;
    const battery = t.battery as Record<string, unknown> | undefined;
    const link = t.link as Record<string, unknown> | undefined;
    const rc = t.rc as Record<string, unknown> | undefined;
    const lte = t.lte as Record<string, unknown> | undefined;
    const telemetryBlock = t.telemetry as Record<string, unknown> | undefined;
    const status = t.status as Record<string, unknown> | undefined;

    const batteryCellsRaw =
      battery?.cells ??
      battery?.cell_voltages ??
      t.battery_cells ??
      t.cell_voltages ??
      null;
    const batteryCells = Array.isArray(batteryCellsRaw) ? batteryCellsRaw : null;

    const linkRc = link?.rc ?? rc?.quality ?? t.rc_quality ?? t.rssi ?? null;
    const linkLte = link?.lte ?? lte?.quality ?? t.lte_quality ?? null;
    const linkTelemetry =
      link?.telemetry ?? telemetryBlock?.quality ?? t.telemetry_quality ?? null;

    const failsafeRaw =
      (t.failsafe as Record<string, unknown> | undefined)?.state ??
      t.failsafe_state ??
      status?.failsafe ??
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

    return {
      flightStatus: telemetrySummary.flightStatus,
      gpsStrength: telemetrySummary.gpsStrength,
      batteryHealth: telemetrySummary.batteryHealth,
      failsafeState: telemetrySummary.failsafe,
      altitudeDisplay: telemetrySummary.alt,
      batteryCellDisplay,
      linkQuality,
      windDisplay: telemetrySummary.wind,
      failsafeActive,
      heading: status?.heading ?? t.heading ?? t.yaw ?? null,
      armed: Boolean(t.armed ?? status?.armed),
    };
  }, [telemetry]);
}
