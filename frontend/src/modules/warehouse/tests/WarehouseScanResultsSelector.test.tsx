import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WarehouseScanResultsSelector } from "../components/WarehouseScanResultsSelector";
import type { WarehouseScannedMapResponse } from "../types/missions";

const SCAN: WarehouseScannedMapResponse = {
  job_id: 7,
  model_id: 2,
  model_version: 1,
  warehouse_map_id: 3,
  warehouse_name: "North warehouse",
  status: "completed",
  source: "simulation",
  created_at: "2026-06-18T12:00:00Z",
  polygon_local_m: [],
  assets: [],
};

describe("WarehouseScanResultsSelector", () => {
  it("locks map switching while replay is loading", () => {
    render(
      <WarehouseScanResultsSelector
        maps={[SCAN]}
        selectedMap={SCAN}
        loading={false}
        disabled
        onSelect={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Previous Scan Results")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("button", { name: "Refresh scan results" })).toBeDisabled();
  });
});
