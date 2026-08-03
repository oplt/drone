import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as agricultureApi from "../api";
import AgricultureFieldListPage from "./AgricultureFieldListPage";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/dashboard/agriculture/fields"]}>
        <AgricultureFieldListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgricultureFieldListPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders empty state without pretending health data exists", async () => {
    vi.spyOn(agricultureApi, "listAgricultureFieldOverviews").mockResolvedValue(
      [],
    );
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/No agriculture fields yet/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/health summaries/i)).toBeInTheDocument();
  });

  it("renders field links and map preview from owned field features", async () => {
    vi.spyOn(agricultureApi, "listAgricultureFieldOverviews").mockResolvedValue(
      [
        {
          id: 7,
          name: "North block",
          area_ha: 2.4,
          workflow_scope: "agriculture",
          geometry_geojson: {
            type: "Polygon",
            coordinates: [
              [
                [4, 50],
                [4.001, 50],
                [4.001, 50.001],
                [4, 50],
              ],
            ],
          },
          profile: { crop_type: "wheat", growth_stage: "tillering" },
          latest_flight: null,
        },
      ],
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("North block")).toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: /North block/i })).toHaveAttribute(
      "href",
      "/dashboard/agriculture/fields/7",
    );
    expect(
      screen.getByRole("img", { name: /Agriculture analysis map layer/i }),
    ).toBeInTheDocument();
  });

  it("renders a retryable error state", async () => {
    vi.spyOn(agricultureApi, "listAgricultureFieldOverviews").mockRejectedValue(
      new Error("offline"),
    );
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/Agriculture fields unavailable/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
