import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AgricultureAnalysisReadiness } from "../types";
import { AgricultureCapabilitySelector } from "./AgricultureCapabilitySelector";

const readiness: AgricultureAnalysisReadiness = {
  catalog_version: "agriculture-capabilities.v1",
  flight_id: "flight-1",
  mission_id: "mission-1",
  ready: true,
  media_count: 1,
  sensor_inventory: ["rgb"],
  capture_prerequisites: [],
  capabilities: [
    {
      id: "quality",
      label: "Capture quality",
      description: "Checks the capture.",
      available: true,
      recommended: true,
      unavailable_reasons: [],
      required_sensor: "rgb",
      required_media: "video",
      requires_model: false,
      output_type: "quality_gate",
      action_relevance: "reflight",
      advanced_defaults: {},
      release: null,
    },
    {
      id: "weed_detection",
      label: "Weed detection",
      description: "Finds weeds.",
      available: false,
      recommended: false,
      unavailable_reasons: ["No production Vision model is released for this capability."],
      required_sensor: "rgb",
      required_media: "video",
      requires_model: true,
      output_type: "observations",
      action_relevance: "field_review",
      advanced_defaults: {},
      release: null,
    },
  ],
};

describe("AgricultureCapabilitySelector", () => {
  it("keeps unavailable capabilities disabled and submits only selected ready work", () => {
    const onSelected = vi.fn();
    const onStart = vi.fn();
    render(
      <AgricultureCapabilitySelector
        readiness={readiness}
        selected={["quality"]}
        loading={false}
        error={false}
        pending={false}
        onSelected={onSelected}
        onRetry={vi.fn()}
        onStart={onStart}
      />,
    );

    expect(screen.getByRole("checkbox", { name: /capture quality/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /weed detection/i })).toBeDisabled();
    expect(screen.getByText(/no production vision model/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /start selected analyses/i }));
    expect(onStart).toHaveBeenCalledOnce();
    expect(onSelected).not.toHaveBeenCalled();
  });
});
