import { render, screen } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LabelingWorkspacePage } from "./LabelingWorkspacePage";

vi.mock("../hooks/useVisionModels", () => ({
  useVisionDataset: () => ({
    data: { id: "ds-1", project_id: "p1", name: "Demo" },
    isLoading: false,
  }),
  useVisionImages: () => ({
    data: {
      items: [
        {
          id: "img-1",
          content_url: "/media/frame-1.jpg",
          reviewed: false,
          annotations: [],
        },
      ],
      total: 1,
    },
    isLoading: false,
    refetch: vi.fn(),
  }),
  useVisionProjects: () => ({
    data: [{ id: "p1", classes: [{ id: "c1", name: "weed" }] }],
  }),
}));

vi.mock("../hooks/useLabelingPersistence", () => ({
  useLabelingPersistence: () => ({
    annotations: [],
    reviewed: false,
    saveState: "idle",
    saveError: null,
    persist: vi.fn(),
    awaitSaves: vi.fn(async () => true),
    deleteSelected: vi.fn(),
    setSelectedId: vi.fn(),
    loadServerVersion: vi.fn(),
  }),
}));

vi.mock("../hooks/useLabelingShortcuts", () => ({
  useLabelingShortcuts: () => undefined,
}));

vi.mock("../visionApi", () => ({
  resolveVisionMediaUrl: (url: string) => url,
}));

function forceMobileViewport() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: /max-width:\s*599/.test(query) || query.includes("max-width:599"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

describe("LabelingWorkspacePage mobile gate", () => {
  beforeEach(() => {
    forceMobileViewport();
  });

  it("shows review-only path under sm without draw canvas", () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter initialEntries={["/dashboard/agriculture/vision-models/datasets/ds-1/label"]}>
          <Routes>
            <Route
              path="/dashboard/agriculture/vision-models/datasets/:datasetId/label"
              element={<LabelingWorkspacePage />}
            />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(
      screen.getByText(/Drawing annotations needs a tablet or laptop/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Mark reviewed/i })).toBeInTheDocument();
    expect(screen.queryByRole("toolbar", { name: /Labeling tools/i })).not.toBeInTheDocument();
  });
});
