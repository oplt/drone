import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgricultureGeometryMapEditor } from "./AgricultureGeometryMapEditor";

vi.mock("../../maps", () => ({
  GoogleMapsContext: {
    Provider: ({ children }: { children: unknown }) => children,
    _currentValue: { isLoaded: false, loadError: undefined },
  },
  MissionMapViewport: ({ mapLibreMapProps }: { mapLibreMapProps?: { focusRequestToken?: number } }) => (
    <div data-testid="map-viewport" data-focus-token={mapLibreMapProps?.focusRequestToken ?? ""} />
  ),
  RouteDrawControls: () => null,
  TerraDrawController: () => null,
}));

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react");
  return {
    ...actual,
    useContext: () => ({ isLoaded: false, loadError: undefined }),
  };
});

describe("AgricultureGeometryMapEditor", () => {
  it("undoes the last vertex instead of clearing the ring", async () => {
    const user = userEvent.setup();
    const onBoundaryChange = vi.fn();
    const ring: [number, number][] = [
      [4, 50],
      [4.01, 50],
      [4.01, 50.01],
      [4, 50.01],
    ];
    render(
      <AgricultureGeometryMapEditor boundary={ring} onBoundaryChange={onBoundaryChange} />,
    );
    await user.click(screen.getByRole("button", { name: "Undo last point" }));
    expect(onBoundaryChange).toHaveBeenCalledWith([
      [4, 50],
      [4.01, 50],
      [4.01, 50.01],
    ]);
  });

  it("clears the boundary with an explicit clear action", async () => {
    const user = userEvent.setup();
    const onBoundaryChange = vi.fn();
    render(
      <AgricultureGeometryMapEditor
        boundary={[[4, 50], [4.01, 50], [4.01, 50.01]]}
        onBoundaryChange={onBoundaryChange}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Clear boundary" }));
    expect(onBoundaryChange).toHaveBeenCalledWith([]);
  });

  it("no-ops location search when Google Maps is not loaded", async () => {
    const user = userEvent.setup();
    render(
      <AgricultureGeometryMapEditor boundary={null} onBoundaryChange={vi.fn()} />,
    );
    await user.type(screen.getByLabelText(/Search location/i), "Ghent farm");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByText(/needs Google Maps/i)).toBeInTheDocument();
  });

  it("passes focusRequestToken through to fit imported boundaries", () => {
    render(
      <AgricultureGeometryMapEditor
        boundary={[[4, 50], [4.01, 50], [4.01, 50.01]]}
        focusRequestToken={3}
        onBoundaryChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId("map-viewport")).toHaveAttribute("data-focus-token", "3");
  });
});
