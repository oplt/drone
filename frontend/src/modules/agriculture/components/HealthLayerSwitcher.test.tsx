import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { describe, expect, it, vi } from "vitest";
import { HealthLayerSwitcher } from "./HealthLayerSwitcher";

describe("HealthLayerSwitcher", () => {
  it("exposes layer and threshold labels for operators", async () => {
    const user = userEvent.setup();
    const onLayerChange = vi.fn();
    const onConfidenceChange = vi.fn();
    const onSeverityChange = vi.fn();

    render(
      <ThemeProvider theme={createTheme()}>
        <HealthLayerSwitcher
          layer="weed"
          onLayerChange={onLayerChange}
          confidence={0.4}
          onConfidenceChange={onConfidenceChange}
          severity={0.2}
          onSeverityChange={onSeverityChange}
        />
      </ThemeProvider>,
    );

    expect(screen.getByLabelText("Health layer controls")).toBeInTheDocument();
    expect(screen.getByLabelText("Health layer")).toBeInTheDocument();
    expect(screen.getByText("Confidence 40%")).toBeInTheDocument();
    expect(screen.getByText("Severity 20%")).toBeInTheDocument();
    expect(screen.getByLabelText("Confidence threshold")).toBeInTheDocument();
    expect(screen.getByLabelText("Severity threshold")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Health layer"));
    await user.click(await screen.findByRole("option", { name: "ndvi" }));
    expect(onLayerChange).toHaveBeenCalledWith("ndvi");
  });
});
