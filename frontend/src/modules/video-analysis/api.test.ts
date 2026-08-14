import { describe, expect, it } from "vitest";
import { resolveWarehouseLiveMapWebSocketUrl } from "../warehouse/api/warehouseLiveMapApi";
import { buildMissionVideoStreamUrl } from "./api";

describe("media URL authentication", () => {
  it("never puts bearer tokens in video stream URLs", () => {
    const url = buildMissionVideoStreamUrl("video-1");
    expect(url).not.toContain("token=");
    expect(url).not.toContain("?");
  });

  it("never puts bearer tokens in warehouse stream URLs", () => {
    const url = resolveWarehouseLiveMapWebSocketUrl("flight-1");
    expect(url).not.toContain("token=");
    expect(url).not.toContain("?");
  });
});
