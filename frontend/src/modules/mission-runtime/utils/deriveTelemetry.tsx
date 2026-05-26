export type TelemetryLike = any;

const toFiniteNumber = (v: any): number | null => {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "") {
    const parsed = Number(v);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const formatMaybeNumber = (v: any, digits = 1) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "--";

export function deriveTelemetry(t: TelemetryLike) {
  const batteryPctRaw =
    t?.battery?.percent ??
    t?.battery?.percentage ??
    t?.battery?.remaining ??
    t?.battery_remaining ??
    t?.batteryPercent ??
    null;

  const batteryPct =
    typeof batteryPctRaw === "number" && batteryPctRaw >= 0 ? batteryPctRaw : null;

  const groundSpeedRaw =
    t?.velocity?.ground ??
    t?.status?.groundspeed ??
    t?.status?.speed ??
    t?.ground_speed ??
    t?.groundSpeed ??
    t?.groundspeed ??
    t?.speed ??
    null;
  const groundSpeed = toFiniteNumber(groundSpeedRaw);

  const relAltRaw =
    t?.position?.rel_alt_m ??
    t?.position?.relative_altitude ??
    t?.position?.relative_alt ??
    t?.status?.alt ??
    t?.position?.alt ??
    t?.altitude?.altitude_relative_m ??
    t?.altitude_relative_m ??
    t?.altitude ??
    t?.relativeAltitude ??
    null;
  const relAlt = toFiniteNumber(relAltRaw);

  let windSpeed =
    toFiniteNumber(t?.wind?.speed) ??
    toFiniteNumber(t?.wind_speed) ??
    toFiniteNumber(t?.windSpeed) ??
    toFiniteNumber(t?.windspeed);
  if (windSpeed === null) {
    const windX =
      toFiniteNumber(t?.wind?.wind_x_ned_m_s) ??
      toFiniteNumber(t?.wind_x_ned_m_s);
    const windY =
      toFiniteNumber(t?.wind?.wind_y_ned_m_s) ??
      toFiniteNumber(t?.wind_y_ned_m_s);
    if (windX !== null || windY !== null) {
      windSpeed = Math.hypot(windX ?? 0, windY ?? 0);
    }
  }

  const mode = t?.status?.mode ?? t?.mode ?? t?.flight_mode ?? null;
  const headingRaw = t?.status?.heading ?? t?.heading ?? t?.yaw ?? null;
  const heading = toFiniteNumber(headingRaw);

  const sats = t?.gps?.satellites ?? t?.satellites ?? null;
  const hdop = t?.gps?.hdop ?? t?.hdop ?? t?.gps_hdop ?? null;

  const armed = Boolean(t?.armed ?? t?.status?.armed);

  const failsafeRaw =
    t?.failsafe?.state ?? t?.failsafe_state ?? t?.status?.failsafe ?? null;

  const failsafeState =
    typeof failsafeRaw === "string" && failsafeRaw.trim() !== ""
      ? failsafeRaw
      : typeof failsafeRaw === "boolean"
        ? failsafeRaw ? "Active" : "None"
        : "--";

  const failsafeActive =
    typeof failsafeRaw === "boolean"
      ? failsafeRaw
      : typeof failsafeRaw === "string"
        ? !["none", "ok", "inactive"].includes(failsafeRaw.toLowerCase())
        : false;

  const flightStatus = failsafeActive
    ? "Emergency"
    : typeof mode === "string" && mode.toUpperCase().includes("RTL")
      ? "RTL"
      : armed && typeof groundSpeed === "number" && groundSpeed > 1
        ? "In Air"
        : armed
          ? "Armed"
          : "Idle";

  const gpsStrength =
    sats === null && hdop === null ? "--" : `${sats ?? "--"} sats • HDOP ${formatMaybeNumber(hdop, 1)}`;

  const fixTypeRaw = t?.gps?.fix_type ?? t?.gps_fix_type ?? t?.fix_type ?? null;
  const fixType = toFiniteNumber(fixTypeRaw);
  const gpsShort =
    fixType !== null
      ? fixType >= 6
        ? "GPS RTK"
        : fixType >= 4
          ? "GPS 3D"
          : fixType >= 3
            ? "GPS 3D"
            : fixType >= 2
              ? "GPS 2D"
              : "GPS NO FIX"
      : typeof sats === "number" && sats >= 6
        ? "GPS 3D"
        : typeof sats === "number" && sats > 0
          ? "GPS 2D"
          : "--";

  const batteryHealth =
    typeof batteryPct === "number" && Number.isFinite(batteryPct)
      ? batteryPct >= 60
        ? `Good (${Math.round(batteryPct)}%)`
        : batteryPct >= 30
          ? `Fair (${Math.round(batteryPct)}%)`
          : `Critical (${Math.round(batteryPct)}%)`
      : "--";

  const batteryShort =
    typeof batteryPct === "number" && Number.isFinite(batteryPct)
      ? `BAT ${Math.round(batteryPct)}%`
      : "--";

  const failsafeShort = failsafeActive ? "FS ACTIVE" : "SAFE";
  const statusShort = flightStatus.toUpperCase();
  const modeShort =
    typeof mode === "string" && mode.trim() !== "" ? mode.toUpperCase().replace(/_/g, " ") : "--";
  const speedShort =
    typeof groundSpeed === "number" ? `${formatMaybeNumber(groundSpeed, 1)} m/s` : "--";
  const altShort = typeof relAlt === "number" ? `${formatMaybeNumber(relAlt, 0)} m` : "--";

  return {
    batteryHealth,
    batteryShort,
    gpsStrength,
    gpsShort,
    flightStatus,
    statusShort,
    speed: typeof groundSpeed === "number" ? `${formatMaybeNumber(groundSpeed, 1)} m/s` : "--",
    speedShort,
    alt: typeof relAlt === "number" ? `${formatMaybeNumber(relAlt, 1)} m` : "--",
    altShort,
    wind: typeof windSpeed === "number" ? `${formatMaybeNumber(windSpeed, 1)} m/s` : "--",
    heading: typeof heading === "number" ? `${Math.round(heading)}°` : "--",
    mode: typeof mode === "string" ? mode : "--",
    modeShort,
    failsafe: failsafeState,
    failsafeShort,
    armed,
    sats,
    hdop,
    fixType,
  };
}
