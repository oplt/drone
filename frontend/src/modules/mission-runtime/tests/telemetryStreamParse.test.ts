import { describe, expect, it } from "vitest";
import {
  isTelemetryRecord,
  parseTelemetryMessage,
  telemetryFromMessage,
} from "../realtime/telemetryStreamParse";

describe("telemetryFromMessage", () => {
  it("maps v1 envelope telemetry into snapshot fields", () => {
    const snapshot = telemetryFromMessage({
      type: "telemetry",
      protocol: "v1",
      envelope: {
        payload: {
          position: { lat: 1.2, lon: 3.4, alt_m: 10, relative_alt_m: 5 },
          attitude: { roll_rad: 0.1, pitch_rad: 0.2, yaw_rad: 0.3 },
          battery: { remaining_pct: 0.77, voltage_v: 12.1 },
          motion: { groundspeed_mps: 4.5, heading_deg: 90 },
          flight_mode: "GUIDED",
          armed: true,
        },
      },
    });

    expect(snapshot).toMatchObject({
      position: { lat: 1.2, lon: 3.4, alt: 10, relative_alt: 5 },
      battery: { remaining: 0.77, voltage: 12.1 },
      status: { groundspeed: 4.5, heading: 90 },
      mode: "GUIDED",
      armed: true,
    });
  });

  it("accepts legacy telemetry.data payloads", () => {
    expect(
      telemetryFromMessage({
        type: "telemetry",
        data: { battery: { percent: 55 } },
      }),
    ).toEqual({ battery: { percent: 55 } });
  });

  it("ignores non-telemetry typed messages", () => {
    expect(telemetryFromMessage({ type: "app_log", data: {} })).toBeNull();
  });
});

describe("parseTelemetryMessage", () => {
  it("parses JSON strings", async () => {
    await expect(parseTelemetryMessage('{"type":"pong"}')).resolves.toEqual({
      type: "pong",
    });
  });

  it("returns raw string when JSON parse fails", async () => {
    await expect(parseTelemetryMessage("pong")).resolves.toBe("pong");
  });
});

describe("isTelemetryRecord", () => {
  it("accepts plain objects only", () => {
    expect(isTelemetryRecord({ ok: true })).toBe(true);
    expect(isTelemetryRecord(null)).toBe(false);
    expect(isTelemetryRecord([])).toBe(false);
  });
});
