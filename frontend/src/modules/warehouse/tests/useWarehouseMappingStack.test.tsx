import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTestQueryWrapper } from "../../../test/renderWithProviders";
import { fetchWarehouseMappingStackStatus } from "../api/warehouseMissionsApi";
import { useWarehouseMappingStack } from "../hooks/useWarehouseMappingStack";

vi.mock("../api/warehouseMissionsApi", () => ({
  fetchWarehouseMappingStackStatus: vi.fn(),
}));

describe("useWarehouseMappingStack", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWarehouseMappingStackStatus).mockResolvedValue({
      running: true,
      pid: 42,
      started_at: "2026-06-18T00:00:00Z",
      last_exit_code: null,
      last_error: null,
      phase: "running",
    });
  });

  it("shares one request between observers", async () => {
    const wrapper = createTestQueryWrapper();
    const first = renderHook(
      () => useWarehouseMappingStack({ getToken: () => "token" }),
      { wrapper },
    );
    const second = renderHook(
      () => useWarehouseMappingStack({ getToken: () => "token" }),
      { wrapper },
    );

    await waitFor(() => expect(first.result.current.mappingStackStatus).not.toBeNull());
    expect(second.result.current.mappingStackStatus?.running).toBe(true);
    expect(fetchWarehouseMappingStackStatus).toHaveBeenCalledTimes(1);
  });

  it("does not request status when disabled", () => {
    const { result } = renderHook(
      () =>
        useWarehouseMappingStack({
          enabled: false,
          getToken: () => "token",
        }),
      { wrapper: createTestQueryWrapper() },
    );

    expect(result.current.mappingStackStatus).toBeNull();
    expect(fetchWarehouseMappingStackStatus).not.toHaveBeenCalled();
  });
});
