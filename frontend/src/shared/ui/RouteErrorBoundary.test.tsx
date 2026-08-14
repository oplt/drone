import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { RouteErrorBoundary } from "./RouteErrorBoundary";

function Boom(): never {
  throw new Error("forced route failure");
}

describe("RouteErrorBoundary", () => {
  it("shows ErrorState and recovers on retry", async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("forced route failure");
      return <div>recovered view</div>;
    }

    render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <RouteErrorBoundary>
            <Flaky />
          </RouteErrorBoundary>
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByText("View failed to load")).toBeInTheDocument();
    expect(screen.getByText(/forced route failure/i)).toBeInTheDocument();

    shouldThrow = false;
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(screen.getByText("recovered view")).toBeInTheDocument();

    consoleError.mockRestore();
  });

  it("renders ErrorState for hard throw", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <RouteErrorBoundary>
            <Boom />
          </RouteErrorBoundary>
        </MemoryRouter>
      </ThemeProvider>,
    );
    expect(screen.getByText("View failed to load")).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
