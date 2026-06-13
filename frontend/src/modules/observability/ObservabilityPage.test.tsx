import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ObservabilityPage from "./ObservabilityPage";
import * as observabilityApi from "./api";
import type { ObservabilityLinks, ObservabilityStatus } from "./types";

vi.mock("../session", () => ({
  useCurrentUser: vi.fn(() => ({
    user: { id: 1, email: "operator@example.com", role: "operator" },
  })),
}));

vi.mock("../../shared/layout/WorkflowHeader", () => ({
  default: () => null,
}));

const configuredLinks: ObservabilityLinks = {
  grafanaBaseUrl: "https://grafana.example.com",
  prometheusUrl: "https://prometheus.example.com/graph",
  fleetDashboardUrl: "https://grafana.example.com/d/drone-fleet/fleet-health",
  apiDashboardUrl: "https://grafana.example.com/d/drone-api/api-observability",
  workersDashboardUrl: "https://grafana.example.com/d/drone-workers/worker-observability",
  videoDashboardUrl: "https://grafana.example.com/d/drone-video/video-pipeline",
  mavlinkDashboardUrl: "https://grafana.example.com/d/drone-mavlink/mavlink-telemetry",
  tracesUrl: "https://grafana.example.com/explore",
};

const configuredStatus: ObservabilityStatus = {
  api: { status: "healthy" },
  prometheus: { status: "healthy", url: configuredLinks.prometheusUrl },
  grafana: { status: "healthy", url: configuredLinks.grafanaBaseUrl },
  tempo: { status: "unknown", url: configuredLinks.tracesUrl },
  telemetry: { status: "unknown", lagSeconds: null },
  workers: { status: "unknown", queueDepth: null },
};

function renderPage(children: ReactNode = <ObservabilityPage />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/observability"]}>{children}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ObservabilityPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(observabilityApi, "fetchObservabilityLinks").mockResolvedValue(configuredLinks);
    vi.spyOn(observabilityApi, "fetchObservabilityStatus").mockResolvedValue(configuredStatus);
  });

  it("renders configured state and hides Prometheus Debug for non-admin users", async () => {
    renderPage();

    expect(screen.getByText("Observability")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Fleet Health")).toBeInTheDocument();
    });

    expect(screen.queryByText("Prometheus Debug")).not.toBeInTheDocument();
    expect(screen.getByText("Tempo Traces")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Open dashboard/i }).length).toBeGreaterThan(0);
  });

  it("renders loading and missing-config states", async () => {
    vi.spyOn(observabilityApi, "fetchObservabilityLinks").mockResolvedValue({
      ...configuredLinks,
      apiDashboardUrl: null,
      workersDashboardUrl: null,
    });

    renderPage();

    expect(screen.getAllByText(/Observability/i).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getAllByText("Not configured").length).toBeGreaterThan(0);
    });
  });
});
