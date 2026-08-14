import { describe, expect, it } from "vitest";
import { formatTelemetryHudModelName } from "../components/telemetryHud/telemetryHudFormatters";

describe("formatTelemetryHudModelName", () => {
  it("strips path and normalizes model basename", () => {
    expect(formatTelemetryHudModelName("weights/yolov8n.pt")).toBe("YOLOV8N");
    expect(formatTelemetryHudModelName("custom_model-v2.pt")).toBe("CUSTOMMODELV2");
  });

  it("returns null for empty input", () => {
    expect(formatTelemetryHudModelName(null)).toBeNull();
    expect(formatTelemetryHudModelName(undefined)).toBeNull();
  });
});
