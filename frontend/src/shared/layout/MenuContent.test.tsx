import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import MenuContent from "./MenuContent";

function renderMenu(path: string) {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<MenuContent userRole="admin" />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("MenuContent nav selection", () => {
  it("selects Operations only on exact /dashboard", () => {
    renderMenu("/dashboard");
    const ops = screen.getByRole("link", { name: "Operations" });
    expect(ops).toHaveClass("Mui-selected");
  });

  it("does not keep Operations selected on nested dashboard routes", () => {
    renderMenu("/dashboard/fleet");
    const ops = screen.getByRole("link", { name: "Operations" });
    expect(ops).not.toHaveClass("Mui-selected");
    const fleet = screen.getByRole("link", { name: "Fleet" });
    expect(fleet).toHaveClass("Mui-selected");
  });

  it("exposes Agriculture Fields and Video Analysis destinations", () => {
    renderMenu("/dashboard/agriculture/fields");
    expect(
      screen.getByRole("link", { name: "Agriculture Fields" }),
    ).toHaveClass("Mui-selected");
    expect(
      screen.getByRole("link", { name: "Video Analysis" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Field Survey" }),
    ).toBeInTheDocument();
  });

  it("keeps Tasks expand-only (not a link to Controlled Flight)", async () => {
    const user = userEvent.setup();
    renderMenu("/dashboard/fleet");
    expect(screen.queryByRole("link", { name: "Tasks" })).not.toBeInTheDocument();
    const tasksToggle = screen.getByRole("button", { name: /Tasks/i });
    expect(tasksToggle).toBeInTheDocument();
    await user.click(tasksToggle);
    expect(
      screen.getByRole("link", { name: "Controlled Flight" }),
    ).toHaveAttribute("href", "/dashboard/controlled");
  });
});
