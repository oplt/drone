import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchWarehouseMappingStackStatus } from "../api/warehouseMissionsApi";
import { useWarehouseMappingStack } from "../hooks/useWarehouseMappingStack";

vi.mock("../api/warehouseMissionsApi", () => ({
  fetchWarehouseMappingStackStatus: vi.fn(),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

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
    const wrapper = createWrapper();
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
      { wrapper: createWrapper() },
    );

    expect(result.current.mappingStackStatus).toBeNull();
    expect(fetchWarehouseMappingStackStatus).not.toHaveBeenCalled();
  });
});
