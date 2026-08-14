import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import DashboardAlertsPanel from "./DashboardAlertsPanel";
import {
  sortDashboardAlerts,
  toMuiSeverity,
  type DashboardAlertItem,
} from "../utils/dashboardAlerts";

describe("DashboardAlertsPanel", () => {
  it("sorts critical before medium and newer first within severity", () => {
    const items: DashboardAlertItem[] = [
      {
        id: "1",
        title: "Old medium",
        message: "m",
        severity: "medium",
        triggeredAt: "2024-01-01T00:00:00Z",
      },
      {
        id: "2",
        title: "Critical now",
        message: "c",
        severity: "critical",
        triggeredAt: "2024-06-01T00:00:00Z",
      },
      {
        id: "3",
        title: "Newer medium",
        message: "m2",
        severity: "medium",
        triggeredAt: "2024-06-02T00:00:00Z",
      },
    ];
    expect(sortDashboardAlerts(items).map((i) => i.id)).toEqual(["2", "3", "1"]);
    expect(toMuiSeverity("critical")).toBe("error");
  });

  it("distinguishes load failure from empty quiet state", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = render(
      <ThemeProvider theme={createTheme()}>
        <DashboardAlertsPanel items={[]} loadError="network down" onRetryLoad={onRetry} />
      </ThemeProvider>,
    );
    expect(screen.getByText(/Failed to load alerts/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Retry alerts/i }));
    expect(onRetry).toHaveBeenCalled();

    rerender(
      <ThemeProvider theme={createTheme()}>
        <DashboardAlertsPanel items={[]} loadError={null} />
      </ThemeProvider>,
    );
    expect(screen.getByText(/No open alerts/i)).toBeInTheDocument();
  });

  it("renders critical with error severity styling", () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <DashboardAlertsPanel
          items={[
            {
              id: "c1",
              title: "Battery critical",
              message: "low",
              severity: "critical",
              triggeredAt: "2024-06-01T00:00:00Z",
            },
          ]}
        />
      </ThemeProvider>,
    );
    const alert = screen.getByRole("alert");
    expect(alert.className).toMatch(/MuiAlert-standardError|MuiAlert-filledError|error/i);
    expect(screen.getByText("Battery critical")).toBeInTheDocument();
  });
});
