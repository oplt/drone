import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgricultureFieldSetupWizard } from "./AgricultureFieldSetupWizard";

const mutate = vi.fn();

vi.mock("../hooks", () => ({
  useCreateAgricultureField: () => ({
    mutate,
    isPending: false,
    isError: false,
  }),
  usePatchAgricultureProfile: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
}));

vi.mock("./AgricultureGeometryMapEditor", () => ({
  AgricultureGeometryMapEditor: ({ onBoundaryChange }: { onBoundaryChange: (ring: [number, number][]) => void }) => (
    <div>
      <span>Click boundary points on the map.</span>
      <button onClick={() => onBoundaryChange([[4, 50], [4.01, 50], [4.01, 50.01], [4, 50.01]])}>
        Draw test boundary
      </button>
    </div>
  ),
}));

describe("AgricultureFieldSetupWizard", () => {
  beforeEach(() => mutate.mockReset());

  it("guides keyboard users through all setup steps", async () => {
    const user = userEvent.setup();
    render(<AgricultureFieldSetupWizard />);
    await user.type(screen.getByLabelText(/Field name/i), "North field");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText(/Click boundary points/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Draw test boundary" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByLabelText("Crop type")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("North field")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create field" })).toBeEnabled();
  });

  it("explains missing and self-intersecting geometry", async () => {
    const user = userEvent.setup();
    render(<AgricultureFieldSetupWizard />);
    await user.type(screen.getByLabelText(/Field name/i), "South field");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Draw or import/i);

    await user.click(screen.getByText("Advanced GeoJSON"));
    fireEvent.change(screen.getByLabelText(/Boundary GeoJSON/i), {
      target: { value: JSON.stringify({ type: "Polygon", coordinates: [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]] }) },
    });
    await user.click(screen.getByRole("button", { name: "Apply GeoJSON" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/crosses itself/i);
  });
});
