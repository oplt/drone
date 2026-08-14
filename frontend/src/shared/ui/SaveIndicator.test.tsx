import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { labelingSaveToIndicator } from "./saveIndicatorState";
import { SaveIndicator } from "./SaveIndicator";

describe("SaveIndicator", () => {
  it("maps labeling save states", () => {
    expect(labelingSaveToIndicator("saving")).toBe("saving");
    expect(labelingSaveToIndicator("failed")).toBe("error");
    expect(labelingSaveToIndicator("saved")).toBe("saved");
  });

  it("announces dirty and error states", () => {
    const { rerender } = render(<SaveIndicator state="dirty" />);
    expect(screen.getByRole("status")).toHaveTextContent("Unsaved changes");
    rerender(<SaveIndicator state="error" />);
    expect(screen.getByRole("status")).toHaveTextContent("Save failed");
  });
});
