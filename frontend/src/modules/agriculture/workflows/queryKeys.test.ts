import { describe, expect, it, vi } from "vitest";
import {
  agricultureInvalidationKeys,
  agricultureKeys,
  agriculturePollInterval,
} from "./queryKeys";

describe("agriculture invalidation keys", () => {
  it("targets media inventory queries without invalidating agriculture globally", () => {
    expect(agricultureInvalidationKeys.mediaInventories()).toEqual([
      "agriculture",
      "media-inventory",
    ]);
    expect(agricultureInvalidationKeys.mediaInventories()).not.toEqual(
      agricultureKeys.all,
    );
  });

  it("targets observation lists without invalidating unrelated workflows", () => {
    expect(agricultureInvalidationKeys.observations()).toEqual([
      "agriculture",
      "observations",
    ]);
  });

  it("pauses polling for inactive or hidden workflows", () => {
    expect(agriculturePollInterval(3000, false)).toBe(false);
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    expect(agriculturePollInterval(3000)).toBe(false);
    visibility.mockRestore();
    expect(agriculturePollInterval(3000)).toBe(3000);
  });
});
