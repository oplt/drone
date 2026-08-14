import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { PageSection } from "../../../shared/layout/PageLayout";
import {
  TelemetryReadout,
  TelemetryReadoutRow,
} from "../../mission-runtime/components/TelemetryReadout";

type DashboardTelemetryPanelProps = {
  isConnected: boolean;
  mode: string;
  altitudeM: number;
  speedMps: number;
  batteryPct: number | null;
  satellites: number;
  hdop: number;
  gpsQualityScore?: number | null;
  gpsStrength?: string;
  batteryShort?: string;
  gpsShort?: string;
  speedShort?: string;
  altShort?: string;
  modeShort?: string;
};

export default function DashboardTelemetryPanel({
  isConnected,
  mode,
  altitudeM,
  speedMps,
  batteryPct,
  satellites,
  hdop,
  gpsQualityScore = null,
  gpsStrength,
  batteryShort,
  gpsShort,
  speedShort,
  altShort,
  modeShort,
}: DashboardTelemetryPanelProps) {
  const modeValue = modeShort ?? mode;
  const altValue =
    altShort ??
    (Number.isFinite(altitudeM) ? `${altitudeM.toFixed(1)} m` : "--");
  const speedValue =
    speedShort ??
    (Number.isFinite(speedMps) ? `${speedMps.toFixed(1)} m/s` : "--");
  const batteryValue =
    batteryShort ??
    (batteryPct !== null ? `BAT ${Math.round(batteryPct)}%` : "BAT --");
  const gpsDetail =
    gpsStrength ??
    `${Number.isFinite(satellites) ? satellites : "--"} sats • HDOP ${
      Number.isFinite(hdop) ? hdop.toFixed(1) : "--"
    }`;
  const gpsLabel = gpsShort ?? "GPS";
  const batteryWarn = batteryPct !== null && batteryPct < 30;
  const batteryError = batteryPct !== null && batteryPct < 15;

  return (
    <PageSection
      title="Live telemetry"
      description="Compact vehicle health snapshot."
      sx={{ height: "100%" }}
      action={
        <Tooltip title="WebSocket telemetry stream state" arrow>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 600,
              color: isConnected ? "success.main" : "text.secondary",
            }}
          >
            {isConnected ? "LIVE" : "OFFLINE"}
          </Typography>
        </Tooltip>
      }
    >
      <Stack spacing={2}>
        <TelemetryReadoutRow>
          <TelemetryReadout
            label="Mode"
            value={modeValue}
            tooltip="Current autopilot mode reported by telemetry."
          />
          <TelemetryReadout
            label="Altitude"
            value={altValue}
            tooltip="Relative altitude above launch/home point."
          />
          <TelemetryReadout
            label="Speed"
            value={speedValue}
            tooltip="Current ground speed in meters per second."
          />
          <TelemetryReadout
            label="Battery"
            value={batteryValue}
            tooltip="Remaining battery percentage from latest telemetry."
            warn={batteryWarn}
            error={batteryError}
          />
        </TelemetryReadoutRow>

        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <Tooltip
            title="GPS fix quality from fix type / HDOP (not satellite count alone)."
            arrow
          >
            <Stack sx={{ flex: 1 }} spacing={0.75}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">
                  {gpsLabel}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{ fontWeight: 600, fontFamily: "ui-monospace, monospace" }}
                >
                  {gpsDetail}
                </Typography>
              </Stack>
              {gpsQualityScore != null ? (
                <LinearProgress
                  variant="determinate"
                  value={gpsQualityScore}
                  sx={{ height: 6, borderRadius: 999 }}
                />
              ) : (
                <Typography variant="caption" color="text.secondary">
                  Fix quality unavailable
                </Typography>
              )}
            </Stack>
          </Tooltip>
          <Tooltip title="Battery reserve from latest telemetry frame." arrow>
            <Stack sx={{ flex: 1 }} spacing={0.75}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">
                  Battery
                </Typography>
                <Typography
                  variant="caption"
                  sx={{ fontWeight: 600, fontFamily: "ui-monospace, monospace" }}
                >
                  {batteryPct !== null ? `${Math.round(batteryPct)}%` : "--"}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={batteryPct ?? 0}
                color={batteryPct !== null && batteryPct < 30 ? "error" : "primary"}
                sx={{ height: 6, borderRadius: 999 }}
              />
            </Stack>
          </Tooltip>
        </Stack>
      </Stack>
    </PageSection>
  );
}
