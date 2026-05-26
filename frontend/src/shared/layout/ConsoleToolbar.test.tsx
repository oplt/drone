import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import ConsoleToolbar from "./ConsoleToolbar";

describe("ConsoleToolbar", () => {
  it("renders breadcrumbs and toolbar actions accessibly", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/dashboard/field"]}>
        <ConsoleToolbar
          leading={<input aria-label="Search fields" />}
          trailing={<button type="button">Alerts</button>}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("toolbar", { name: "Console actions" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search fields")).toBeInTheDocument();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
