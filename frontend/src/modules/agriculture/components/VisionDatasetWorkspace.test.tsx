import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { visionKeys } from "../hooks/useVisionModels";
import type { VisionDataset } from "../visionTypes";
import { VisionDatasetWorkspace } from "./VisionDatasetWorkspace";

const lockedDataset: VisionDataset = {
  id: "dataset-1",
  project_id: "project-1",
  version: 1,
  status: "locked",
  source_count: 1,
  image_count: 3,
  selected_count: 3,
  labeled_count: 3,
  reviewed_count: 3,
  train_count: 1,
  val_count: 1,
  test_count: 1,
  manifest_checksum: "checksum",
  curation_summary: {
    split_leakage_risk: true,
    quality_flags: { split_leakage_risk: true },
    split_leakage: { nearest_cross_split_similarity_count: 2 },
    duplicate_cluster_count: 1,
    near_duplicate_rejected: 1,
  },
  locked_at: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

describe("VisionDatasetWorkspace", () => {
  it("explains immutable snapshots and exposes both vNext recovery paths", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    client.setQueryData(visionKeys.imagePage(lockedDataset.id, 0), {
      items: [],
      total: lockedDataset.image_count,
      offset: 0,
      limit: 200,
    });
    render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <VisionDatasetWorkspace projectId="project-1" dataset={lockedDataset} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText(/snapshot is immutable because training references it/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /create blank vnext/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /clone to vnext/i })).toBeEnabled();
    expect(screen.getByText(/content controls are disabled/i)).toBeVisible();
    expect(screen.getByText(/cross-split leakage detected/i)).toBeVisible();
    expect(screen.getByText(/near-duplicate cluster/i)).toBeVisible();
  });
});
