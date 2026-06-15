import { describe, expect, it } from "vitest";
import { healthStatusTextColor } from "./healthStatusPresentation";

describe("healthStatusPresentation", () => {
  it("maps status to theme color tokens", () => {
    expect(healthStatusTextColor("healthy")).toBe("success.main");
    expect(healthStatusTextColor("unknown")).toBe("text.disabled");
    expect(healthStatusTextColor("degraded")).toBe("error.main");
    expect(healthStatusTextColor("down")).toBe("error.main");
  });
});
