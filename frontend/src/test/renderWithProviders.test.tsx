import { describe, expect, it } from "vitest";

import { createTestQueryClient } from "./renderWithProviders";

describe("createTestQueryClient", () => {
  it("creates isolated clients with the shared query defaults", () => {
    const first = createTestQueryClient();
    const second = createTestQueryClient();

    first.setQueryData(["isolated"], "first-client");

    expect(first).not.toBe(second);
    expect(first.getDefaultOptions().queries?.retry).toBe(false);
    expect(second.getQueryData(["isolated"])).toBeUndefined();
  });
});
