import { act, fireEvent, render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";

describe("AgricultureGeoJsonPreview accessibility", () => {
  it("provides keyboard-operable map features and a semantic list fallback", () => {
    const onSelect = vi.fn();
    render(
      <AgricultureGeoJsonPreview
        onSelect={onSelect}
        geojson={{
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [4, 50] },
              properties: { id: "obs-1", observation_type: "standing_water" },
            },
          ],
        }}
      />,
    );

    const mapFeature = screen.getByRole("button", {
      name: /Select standing water obs-1, Medium severity/i,
    });
    expect(mapFeature.tagName).toBe("BUTTON");
    expect(mapFeature).toBeEnabled();
    expect(
      screen.getByRole("list", { name: "Map feature review list" }),
    ).toBeInTheDocument();
    expect(mapFeature).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "Map severity legend" }),
    ).toBeInTheDocument();
  });

  it("supports arrow-key traversal through the map review list", () => {
    render(
      <AgricultureGeoJsonPreview
        geojson={{
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [4, 50] },
              properties: {
                id: "one",
                observation_type: "weed",
                severity: 0.2,
              },
            },
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [4.1, 50.1] },
              properties: {
                id: "two",
                observation_type: "water",
                severity: 0.9,
              },
            },
          ],
        }}
      />,
    );
    const first = screen.getByRole("button", {
      name: /Select weed one, Low severity/i,
    });
    const second = screen.getByRole("button", {
      name: /Select water two, High severity/i,
    });
    act(() => { first.focus(); fireEvent.keyDown(first, { key: "ArrowDown" }); });
    expect(second).toHaveFocus();
    act(() => { fireEvent.keyDown(second, { key: "ArrowUp" }); });
    expect(first).toHaveFocus();
  });

  it("explains missing geometry without presenting a fake map", () => {
    render(<AgricultureGeoJsonPreview geojson={{ features: [] }} />);
    expect(screen.getByText(/No georeferenced features/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: /Agriculture analysis map layer/i }),
    ).not.toBeInTheDocument();
  });

  it("has no automated axe violations in the interactive state", async () => {
    const { container } = render(
      <AgricultureGeoJsonPreview
        geojson={{
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [4, 50] },
              properties: { id: "obs-1", observation_type: "standing_water" },
            },
          ],
        }}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
