import { describe, expect, it } from "vitest";
import { buildPreflightRows } from "./buildPreflightRows";
import { DEFAULT_PREFLIGHT_SETTINGS } from "./preflightUtils";

describe("buildPreflightRows", () => {
  it("blocks arm when preflight cannot start", () => {
    const rows = buildPreflightRows({
      missionType: "route",
      params: DEFAULT_PREFLIGHT_SETTINGS,
      telemetry: { gps: { hdop: 99 } },
      preflightRun: {
        preflight_run_id: "run-1",
        overall_status: "FAIL",
        can_start_mission: false,
        report: {
          base_checks: [
            { name: "GPS HDOP", status: "FAIL", message: "hdop too high" },
          ],
        },
      },
    });

    const hdop = rows.SYSTEM_STATUS.find((row) => row.id === "hdop");
    expect(hdop?.status).toBe("FAIL");
  });

  it("does not infer pass from stale telemetry when drone is disconnected", () => {
    const rows = buildPreflightRows({
      missionType: "route",
      params: DEFAULT_PREFLIGHT_SETTINGS,
      telemetry: { gps: { hdop: 0.8, satellites_visible: 12 } },
      preflightRun: null,
      droneConnected: false,
    });

    const hdop = rows.SYSTEM_STATUS.find((row) => row.id === "hdop");
    expect(hdop?.status).toBe("NOT_RUN");
    expect(hdop?.statusDetail).toContain("Drone not connected");
  });

  it("skips mission rows for unsupported mission types", () => {
    const rows = buildPreflightRows({
      missionType: "warehouse",
      params: DEFAULT_PREFLIGHT_SETTINGS,
      telemetry: null,
      preflightRun: null,
    });

    expect(rows.MISSION).toHaveLength(0);
    expect(rows.SYSTEM_STATUS.length).toBeGreaterThan(0);
  });
});
