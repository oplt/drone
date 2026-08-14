import { act, fireEvent, render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { AgricultureMapAccessibleList } from "./AgricultureMapAccessibleList";

const features = [
  { id: "obs-1", label: "weed", severity: 0.2 },
  { id: "obs-2", label: "standing water", severity: 0.9 },
];

describe("AgricultureMapAccessibleList", () => {
  it("supports selection and arrow-key traversal", () => {
    const onSelect = vi.fn();
    render(
      <AgricultureMapAccessibleList
        features={features}
        selectedId="obs-1"
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByText(/Review mapped features without using the map/i));
    const first = screen.getByRole("button", { name: /Select weed obs-1/i });
    const second = screen.getByRole("button", {
      name: /Select standing water obs-2/i,
    });
    act(() => {
      first.focus();
      fireEvent.keyDown(first, { key: "ArrowDown" });
    });
    expect(second).toHaveFocus();
    fireEvent.click(second);
    expect(onSelect).toHaveBeenCalledWith("obs-2");
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <AgricultureMapAccessibleList features={features} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
