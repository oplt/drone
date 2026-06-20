import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const queryMocks = vi.hoisted(() => ({
  preflightRefetch: vi.fn(),
  transitionsRefetch: vi.fn(),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ flightId: "flight-1" }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: null, error: null }),
  useQueries: () => [
    {
      data: {
        mission_name: "Inspection",
        mission_type: "warehouse",
        state: "completed",
        created_at: 1,
      },
      error: null,
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    },
    {
      data: null,
      error: new Error("Preflight request failed"),
      isError: true,
      isFetching: false,
      isLoading: false,
      refetch: queryMocks.preflightRefetch,
    },
    {
      data: null,
      error: new Error("Transition request failed"),
      isError: true,
      isFetching: false,
      isLoading: false,
      refetch: queryMocks.transitionsRefetch,
    },
    {
      data: [],
      error: null,
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    },
    {
      data: [],
      error: null,
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    },
    {
      data: null,
      error: null,
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    },
  ],
}));

import MissionTimeline from "./MissionTimeline";

beforeEach(() => {
  vi.clearAllMocks();
});

it("keeps successful data visible and retries failed sections independently", () => {
  render(<MissionTimeline />);

  expect(screen.getByText("Inspection")).toBeInTheDocument();
  expect(screen.getByText("Preflight unavailable")).toBeInTheDocument();
  expect(screen.getByText("Transitions unavailable")).toBeInTheDocument();
  expect(screen.queryByText("No timeline events recorded.")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retry Preflight" }));

  expect(queryMocks.preflightRefetch).toHaveBeenCalledOnce();
  expect(queryMocks.transitionsRefetch).not.toHaveBeenCalled();
});
