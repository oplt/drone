import { describe, expect, it } from "vitest";
import { deviceStatusColor } from "../utils/fleetDeviceStatus";

describe("fleetDeviceStatus characterization", () => {
  it("maps device readiness statuses to chip colors", () => {
    expect(deviceStatusColor("airworthy")).toBe("success");
    expect(deviceStatusColor("grounded")).toBe("error");
    expect(deviceStatusColor("limited")).toBe("warning");
    expect(deviceStatusColor("unknown")).toBe("default");
  });
});
