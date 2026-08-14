import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import MenuContent from "./MenuContent";

function renderMenu(path: string, userRole = "operator") {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<MenuContent userRole={userRole} />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("MenuContent nav selection", () => {
  it("selects Overview only on exact /dashboard", () => {
    renderMenu("/dashboard");
    const overview = screen.getByRole("link", { name: "Overview" });
    expect(overview).toHaveClass("Mui-selected");
  });

  it("does not keep Overview selected on nested dashboard routes", () => {
    renderMenu("/dashboard/fleet");
    const overview = screen.getByRole("link", { name: "Overview" });
    expect(overview).not.toHaveClass("Mui-selected");
    const fleet = screen.getByRole("link", { name: "Fleet" });
    expect(fleet).toHaveClass("Mui-selected");
  });

  it("exposes grouped Applications and AI destinations for operators", () => {
    renderMenu("/dashboard/agriculture/fields", "operator");
    expect(screen.getByRole("link", { name: "Agriculture" })).toHaveClass(
      "Mui-selected",
    );
    expect(screen.getByRole("link", { name: "Video Analysis" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Missions" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "System" })).not.toBeInTheDocument();
  });

  it("hides mission execution destinations for viewers", async () => {
    const user = userEvent.setup();
    renderMenu("/dashboard/fleet", "viewer");
    expect(screen.queryByRole("link", { name: "Missions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Live Operations" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Applications/i }));
    expect(screen.getByRole("link", { name: "Agriculture" })).toBeInTheDocument();
  });

  it("keeps Applications expand-only and hides observability from operators", async () => {
    const user = userEvent.setup();
    renderMenu("/dashboard/fleet", "operator");
    expect(screen.queryByRole("link", { name: "Applications" })).not.toBeInTheDocument();
    const applicationsToggle = screen.getByRole("button", { name: /Applications/i });
    await user.click(applicationsToggle);
    expect(screen.getByRole("link", { name: "Warehouse" })).toHaveAttribute(
      "href",
      "/dashboard/warehouse",
    );
    expect(screen.queryByRole("link", { name: "System" })).not.toBeInTheDocument();
  });

  it("shows administration destinations for org admins", () => {
    renderMenu("/dashboard/fleet", "org_admin");
    expect(screen.getByRole("link", { name: "System" })).toHaveAttribute(
      "href",
      "/dashboard/observability",
    );
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute(
      "href",
      "/dashboard/admin",
    );
  });
});
