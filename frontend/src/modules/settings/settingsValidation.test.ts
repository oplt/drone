import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS_DOC } from "./settingsDefaults";
import { validateSettingsDoc } from "./settingsValidation";

describe("settingsValidation", () => {
  it("rejects battery min percent outside 10-50", () => {
    const doc = {
      ...DEFAULT_SETTINGS_DOC,
      preflight: { ...DEFAULT_SETTINGS_DOC.preflight, BATTERY_MIN_PERCENT: 5 },
    };
    expect(validateSettingsDoc(doc)).toContain("Battery Min (%)");
  });

  it("rejects bank angle above 45 degrees", () => {
    const doc = {
      ...DEFAULT_SETTINGS_DOC,
      preflight: { ...DEFAULT_SETTINGS_DOC.preflight, BANK_MAX_DEG: 50 },
    };
    expect(validateSettingsDoc(doc)).toContain("Bank angle");
  });

  it("accepts default settings document", () => {
    expect(validateSettingsDoc(DEFAULT_SETTINGS_DOC)).toBeNull();
  });
});
