import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "jest-axe";
import ConfirmDialog from "./ConfirmDialog";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import PageLoader from "./PageLoader";
import PermissionDenied from "./PermissionDenied";

describe("shared ui primitives", () => {
  it("PageLoader exposes loading status semantics", async () => {
    const { container } = render(<PageLoader title="Loading missions" />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("ErrorState supports retry action", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Network unavailable" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("EmptyState renders title and description", () => {
    render(
      <EmptyState title="No missions" description="Create a field mission to begin." />,
    );
    expect(screen.getByRole("heading", { name: "No missions" })).toBeInTheDocument();
    expect(screen.getByText(/Create a field mission/)).toBeInTheDocument();
  });

  it("PermissionDenied exposes alert semantics", () => {
    render(<PermissionDenied onGoBack={() => undefined} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("ConfirmDialog supports keyboard focus on confirm action", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Abort mission"
        description="This will stop the active flight immediately."
        confirmLabel="Abort"
        confirmColor="error"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    const confirmButton = screen.getByRole("button", { name: "Abort" });
    expect(confirmButton).toHaveFocus();
    fireEvent.click(confirmButton);
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
