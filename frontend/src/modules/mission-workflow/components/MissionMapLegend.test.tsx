import { render, screen } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { describe, expect, it } from "vitest";
import { MissionMapLegend } from "./MissionMapLegend";

describe("MissionMapLegend", () => {
  it("exposes labeled map layer chrome for operators", () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <MissionMapLegend />
      </ThemeProvider>,
    );
    expect(screen.getByLabelText("Map layers")).toBeInTheDocument();
    expect(screen.getByText("Work legs")).toBeInTheDocument();
    expect(screen.getByText("Planned route")).toBeInTheDocument();
  });
});
