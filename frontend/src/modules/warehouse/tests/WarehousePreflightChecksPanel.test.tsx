import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WarehousePreflightChecksPanel } from "../components/WarehousePreflightChecksPanel";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";

const basePreflight: WarehouseGoPreflight = {
  ready_to_fly: false,
  bridge_ok: true,
  gazebo_ok: true,
  sensors_ok: false,
  odom_ok: false,
  localization_ok: false,
  tf_ok: false,
  nvblox_ok: null,
  stability_ok: false,
  vehicle_link_ok: true,
  telemetry_stream_ok: true,
  battery_ok: true,
  perception_stable_for_ms: 0,
  perception_required_stable_ms: 8000,
  ros_topic_count: 10,
  primary_blocker: "SLAM tracking lost",
  blockers: ["SLAM tracking lost", "local odometry unavailable"],
  localization_mode: "visual_slam",
  diagnostics_age_ms: 12000,
  categories: {
    localization: "FAIL",
    nvblox: "DEFERRED",
    sensors: "FAIL",
  },
  blocking_reasons: ["SLAM tracking lost"],
  suggested_actions: [],
  note: "",
};

describe("WarehousePreflightChecksPanel", () => {
  it("shows primary blocker and ready-to-fly gate", () => {
    render(
      <WarehousePreflightChecksPanel
        preflight={basePreflight}
        onRunChecks={() => undefined}
      />,
    );
    expect(screen.getByText(/Ready to fly: NO/i)).toBeInTheDocument();
    expect(screen.getByText(/Primary blocker: SLAM tracking lost/i)).toBeInTheDocument();
  });

  it("labels deferred checks separately from fail", () => {
    render(
      <WarehousePreflightChecksPanel
        preflight={basePreflight}
        onRunChecks={() => undefined}
      />,
    );
    expect(screen.getAllByText("DEFERRED").length).toBeGreaterThan(0);
    expect(screen.getAllByText("FAIL").length).toBeGreaterThan(0);
  });

  it("marks stale diagnostics", () => {
    render(
      <WarehousePreflightChecksPanel
        preflight={basePreflight}
        onRunChecks={() => undefined}
      />,
    );
    expect(screen.getByText(/Diagnostics sample stale/i)).toBeInTheDocument();
  });
});
