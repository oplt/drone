import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { WarehouseLayerBudgetSlider } from "../components/WarehouseLayerBudgetSlider";

it("updates its draft label during drag and commits only on release", () => {
  const onCommit = vi.fn();
  render(
    <WarehouseLayerBudgetSlider
      label="RGB-D colored"
      value={100_000}
      onCommit={onCommit}
    />,
  );
  const slider = screen.getByRole("slider", {
    name: "Maximum points for RGB-D colored",
  });

  const root = slider.closest(".MuiSlider-root");
  if (!(root instanceof HTMLElement)) throw new Error("Slider root missing");
  vi.spyOn(root, "getBoundingClientRect").mockReturnValue({
    bottom: 20,
    height: 20,
    left: 0,
    right: 100,
    top: 0,
    width: 100,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });

  fireEvent.mouseDown(root, { clientX: 50, clientY: 10 });

  expect(screen.getByText("130k")).toBeInTheDocument();
  expect(onCommit).not.toHaveBeenCalled();

  fireEvent.mouseUp(document, { clientX: 50, clientY: 10 });

  expect(onCommit).toHaveBeenCalledOnce();
  expect(onCommit).toHaveBeenCalledWith(130_000);
});
