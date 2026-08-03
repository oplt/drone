import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useBrowserOnline } from "./useBrowserOnline";

describe("useBrowserOnline", () => {
  afterEach(() => {
    act(() => window.dispatchEvent(new Event("online")));
  });

  it("tracks browser offline and recovery events", () => {
    const { result } = renderHook(() => useBrowserOnline());
    act(() => window.dispatchEvent(new Event("offline")));
    expect(result.current).toBe(false);
    act(() => window.dispatchEvent(new Event("online")));
    expect(result.current).toBe(true);
  });
});
