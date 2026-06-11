import { describe, expect, it } from "vitest";
import {
  decodeXyz32,
  decodeXyzrgb32,
} from "../utils/liveMapChunkDecoders";
import { inferLayerKey } from "../utils/liveMapLayerUtils";

describe("liveMapLayerUtils", () => {
  it("infers rgbd chunks by id prefix", () => {
    expect(
      inferLayerKey({
        id: "rgbd_000001",
        kind: "point_cloud",
        sequence: 1,
      }),
    ).toBe("rgbdColored");
  });

  it("prefers explicit layer metadata", () => {
    expect(
      inferLayerKey({
        id: "mid360_000001",
        kind: "point_cloud",
        sequence: 1,
        layer: "nvblox_color",
      }),
    ).toBe("nvbloxColor");
  });
});

describe("liveMapChunkDecoders", () => {
  it("decodes xyz32 buffers", () => {
    const source = new Float32Array([0, 0, 0, 1, 2, 3]);
    const decoded = decodeXyz32(source.buffer, {
      colorMode: "height",
      layer: "mid360LiDAR",
    });
    expect(decoded.pointCount).toBe(2);
    expect(decoded.geometry.getAttribute("position").count).toBe(2);
  });

  it("decodes xyzrgb32 buffers", () => {
    const positions = new Float32Array([0, 0, 0, 1, 0, 0]);
    const colors = new Uint8Array([255, 0, 0, 0, 255, 0]);
    const buffer = new Uint8Array(positions.byteLength + colors.byteLength);
    buffer.set(new Uint8Array(positions.buffer), 0);
    buffer.set(colors, positions.byteLength);

    const decoded = decodeXyzrgb32(buffer.buffer, {
      colorMode: "rgb",
      layer: "rgbdColored",
    });
    expect(decoded.pointCount).toBe(2);
    const colorAttr = decoded.geometry.getAttribute("color");
    expect(colorAttr.getX(0)).toBeCloseTo(1, 2);
    expect(colorAttr.getY(1)).toBeCloseTo(1, 2);
  });
});
