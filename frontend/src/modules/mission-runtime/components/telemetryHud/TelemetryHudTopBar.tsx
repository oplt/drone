import type { DerivedTelemetry } from "../../utils/deriveTelemetry";
import { DetailRow, GlassPanel, HudDivider, HudMetric } from "./telemetryHudPrimitives";

type TelemetryHudTopBarProps = {
  derived: DerivedTelemetry;
  detailsOpen: boolean;
  statusError: boolean;
  gpsWarn: boolean;
  gpsError: boolean;
  batteryWarn: boolean;
  batteryError: boolean;
  failsafeError: boolean;
};

export function TelemetryHudTopBar({
  derived,
  detailsOpen,
  statusError,
  gpsWarn,
  gpsError,
  batteryWarn,
  batteryError,
  failsafeError,
}: TelemetryHudTopBarProps) {
  return (
    <GlassPanel
      sx={{
        position: "absolute",
        top: 8,
        left: 8,
        right: detailsOpen ? 148 : 44,
        maxWidth: "calc(100% - 16px)",
        flexWrap: "wrap",
        rowGap: 0.5,
      }}
    >
      <HudMetric
        label="Status"
        value={derived.statusShort}
        error={statusError}
        warn={derived.statusShort === "ARMED"}
      />
      <HudDivider />
      <HudMetric label="Mode" value={derived.modeShort} />
      <HudDivider />
      <HudMetric label="Speed" value={derived.speedShort} />
      <HudDivider />
      <HudMetric label="Alt" value={derived.altShort} />
      <HudDivider />
      <HudMetric label="GPS" value={derived.gpsShort} warn={gpsWarn} error={gpsError} />
      <HudDivider />
      <HudMetric
        label="Battery"
        value={derived.batteryShort}
        warn={batteryWarn}
        error={batteryError}
      />
      <HudDivider />
      <HudMetric label="Failsafe" value={derived.failsafeShort} error={failsafeError} />
    </GlassPanel>
  );
}
