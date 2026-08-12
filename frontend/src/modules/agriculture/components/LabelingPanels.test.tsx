import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AnnotationDraft } from "./AnnotationCanvas";
import { LabelingFooter } from "./LabelingControls";
import { LabelingClassPanel } from "./LabelingPanels";
import type { VisionClass } from "../visionTypes";

const classes: VisionClass[] = [
  { id: "ripe", name: "ripe_tomato", class_index: 0 },
  { id: "damaged", name: "damaged_tomato", class_index: 1 },
];
const annotations: AnnotationDraft[] = [
  { id: "annotation-1", class_id: "ripe", x1: 100, y1: 80, x2: 260, y2: 210 },
];

describe("labeling workspace panels", () => {
  it("renders the semantic annotation list and supports class selection", () => {
    const chooseClass = vi.fn();
    const selectAnnotation = vi.fn();
    render(
      <LabelingClassPanel
        classes={classes}
        annotations={annotations}
        activeClassId="ripe"
        selectedId={null}
        chooseClass={chooseClass}
        selectAnnotation={selectAnnotation}
        deleteSelected={vi.fn()}
      />,
    );

    expect(screen.getByText("#1 ripe tomato")).toBeVisible();
    fireEvent.click(screen.getByText("[2] damaged tomato"));
    fireEvent.click(screen.getByText("#1 ripe tomato"));
    expect(chooseClass).toHaveBeenCalledWith("damaged");
    expect(selectAnnotation).toHaveBeenCalledWith("annotation-1");
  });

  it("shows and changes image review state", () => {
    const toggleReviewed = vi.fn();
    const { rerender } = render(
      <LabelingFooter
        position={0}
        total={2}
        reviewed={false}
        navigate={vi.fn()}
        toggleReviewed={toggleReviewed}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));
    expect(toggleReviewed).toHaveBeenCalledOnce();
    rerender(
      <LabelingFooter
        position={0}
        total={2}
        reviewed
        navigate={vi.fn()}
        toggleReviewed={toggleReviewed}
      />,
    );
    expect(screen.getByRole("button", { name: "Reviewed" })).toBeVisible();
  });
});
