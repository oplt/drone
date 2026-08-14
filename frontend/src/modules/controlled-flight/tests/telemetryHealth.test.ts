import { describe, expect, it } from "vitest";
import {
  telemetryBatteryPercent,
  telemetryBoolean,
  telemetryGpsFixType,
  telemetryHeartbeatReceived,
} from "../utils/telemetryHealth";

describe("telemetryHealth characterization", () => {
  const sampleTelemetry = {
    battery: { remaining_percent: 72 },
    gps: { fix_type: 3 },
    heartbeat: { last_received: "2026-08-14T10:00:00Z" },
    ekf: { ok: true },
    compass: { healthy: false },
  };

  it("extracts battery, gps, heartbeat, and boolean health fields", () => {
    expect(telemetryBatteryPercent(sampleTelemetry)).toBe(72);
    expect(telemetryGpsFixType(sampleTelemetry)).toBe(3);
    expect(telemetryHeartbeatReceived(sampleTelemetry)).toBe(true);
    expect(telemetryBoolean(sampleTelemetry, ["ekf", "ok"])).toBe(true);
    expect(telemetryBoolean(sampleTelemetry, ["compass", "healthy"])).toBe(false);
  });

  it("returns null or false when telemetry paths are missing", () => {
    expect(telemetryBatteryPercent({})).toBeNull();
    expect(telemetryGpsFixType(null)).toBeNull();
    expect(telemetryHeartbeatReceived({})).toBe(false);
    expect(telemetryBoolean({}, ["ekf", "ok"])).toBeNull();
  });
});
