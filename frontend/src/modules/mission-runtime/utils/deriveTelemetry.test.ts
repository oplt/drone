import { describe, expect, it } from "vitest";
import {
  deriveTelemetry,
  TELEMETRY_CONTRACT_FIXTURE,
  telemetryDisplayStrings,
} from "./deriveTelemetry";

describe("deriveTelemetry contract", () => {
  it("normalizes battery percent and fraction forms", () => {
    expect(deriveTelemetry({ battery: { percent: 77 } }).batteryPct).toBe(77);
    expect(deriveTelemetry({ battery: { remaining: 0.42 } }).batteryPct).toBe(42);
  });

  it("exposes gps quality from fix type, not sats*8", () => {
    const withFix = deriveTelemetry({ gps: { fix_type: 6, satellites: 3, hdop: 9 } });
    expect(withFix.gpsQualityScore).toBe(100);
    expect(withFix.sats).toBe(3);

    const satsOnly = deriveTelemetry({ gps: { satellites: 12 } });
    expect(satsOnly.gpsQualityScore).toBeNull();
  });

  it("derives wind speed consistently", () => {
    expect(deriveTelemetry({ wind: { speed: 4.5 } }).windSpeedMps).toBe(4.5);
    expect(
      deriveTelemetry({ wind: { wind_x_ned_m_s: 3, wind_y_ned_m_s: 4 } }).windSpeedMps,
    ).toBe(5);
  });

  it("same fixture → identical battery% / GPS text for all ops surfaces", () => {
    const derived = deriveTelemetry(TELEMETRY_CONTRACT_FIXTURE);
    const display = telemetryDisplayStrings(derived);

    // Surfaces that should agree on these canonical strings:
    // Dashboard strip, Fleet system-link, Command metrics GPS/battery, HUD, StatusChips.
    const surfaces = {
      dashboard: {
        batteryPct: display.batteryPct,
        batteryShort: display.batteryShort,
        gpsShort: display.gpsShort,
        gpsStrength: display.gpsStrength,
      },
      fleet: {
        batteryPct: display.batteryPct,
        batteryShort: display.batteryShort,
        gpsShort: display.gpsShort,
        gpsStrength: display.gpsStrength,
      },
      command: {
        batteryPct: display.batteryPct,
        batteryShort: display.batteryShort,
        gpsShort: display.gpsShort,
        gpsStrength: display.gpsStrength,
      },
      hud: {
        batteryPct: display.batteryPct,
        batteryShort: display.batteryShort,
        gpsShort: display.gpsShort,
        gpsStrength: display.gpsStrength,
      },
    };

    expect(surfaces.dashboard).toEqual(surfaces.fleet);
    expect(surfaces.fleet).toEqual(surfaces.command);
    expect(surfaces.command).toEqual(surfaces.hud);
    expect(display.batteryPct).toBe(77);
    expect(display.batteryShort).toBe("BAT 77%");
    expect(display.gpsShort).toBe("GPS RTK");
    expect(display.gpsStrength).toBe("14 sats • HDOP 0.8");
  });
});
