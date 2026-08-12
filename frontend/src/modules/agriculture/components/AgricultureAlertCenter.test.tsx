import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgricultureAlertCenter } from "./AgricultureAlertCenter";

vi.mock("../alerts", () => ({
  useAgricultureAlerts: () => ({
    data: {
      items: [{
        id: 9,
        severity: "warning",
        title: "Review capture",
        message: "Coverage is low",
        occurrences: 1,
        assigned_to_user_id: null,
        due_at: null,
      }],
    },
    isLoading: false,
    isError: false,
  }),
  useAgricultureAlertActions: () => ({ mutate: vi.fn(), isPending: false }),
  useAssignAgricultureAlert: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("../../session/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({
    user: { id: 17, email: "reviewer@example.com", first_name: "Ari" },
    isLoading: false,
  }),
}));

describe("AgricultureAlertCenter", () => {
  it("uses the signed-in reviewer dialog instead of a browser prompt", async () => {
    const user = userEvent.setup();
    render(<AgricultureAlertCenter />);
    await user.click(screen.getByRole("button", { name: "Assign" }));
    expect(screen.getByRole("dialog", { name: "Assign reviewer" })).toBeInTheDocument();
    expect(screen.getByText(/signed-in reviewer/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/reviewer user id/i)).not.toBeInTheDocument();
  });
});
