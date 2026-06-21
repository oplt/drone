import { describe, expect, it } from "vitest";
import type { PreflightRunResponse } from "../types";
import {
  collectFailedPreflightChecks,
  describePreflightStartBlock,
  formatPreflightFailureMessage,
  preflightAllowsMissionStart,
} from "./preflightUtils";

const failedPreflight: PreflightRunResponse = {
  preflight_run_id: "pf_test",
  overall_status: "FAIL",
  can_start_mission: false,
  report: {
    summary: { failed: 2 },
    base_checks: [
      { name: "EKF Health", status: "FAIL", message: "EKF not OK" },
      { name: "Vehicle Armable", status: "FAIL", message: "Vehicle not armable" },
    ],
  },
};

describe("preflight mission start helpers", () => {
  it("blocks start when preflight is missing or failed", () => {
    expect(preflightAllowsMissionStart(null)).toBe(false);
    expect(preflightAllowsMissionStart(failedPreflight)).toBe(false);
    expect(describePreflightStartBlock(null)).toContain("Run preflight checks");
    expect(describePreflightStartBlock(failedPreflight)).toContain("EKF Health");
  });

  it("lists failed checks and formats a blocking message", () => {
    expect(collectFailedPreflightChecks(failedPreflight)).toHaveLength(2);
    expect(formatPreflightFailureMessage(failedPreflight)).toContain("Vehicle Armable");
  });

  it("allows start only when can_start_mission is true", () => {
    const passing: PreflightRunResponse = {
      preflight_run_id: "pf_pass",
      overall_status: "PASS",
      can_start_mission: true,
    };
    expect(preflightAllowsMissionStart(passing)).toBe(true);
    expect(describePreflightStartBlock(passing)).toBeNull();
  });
});
