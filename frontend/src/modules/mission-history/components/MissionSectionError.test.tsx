import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { MissionSectionError } from "./MissionSectionError";

it("shows section failure detail and retries only on user action", () => {
  const onRetry = vi.fn();
  render(
    <MissionSectionError
      section="Commands"
      error={new Error("Gateway timeout")}
      onRetry={onRetry}
    />,
  );

  expect(screen.getByText("Commands unavailable")).toBeInTheDocument();
  expect(screen.getByText("Gateway timeout")).toBeInTheDocument();
  expect(onRetry).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Retry Commands" }));

  expect(onRetry).toHaveBeenCalledOnce();
});
