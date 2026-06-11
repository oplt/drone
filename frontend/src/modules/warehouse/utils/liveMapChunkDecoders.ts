import * as THREE from "three";
import type { LiveMapColorMode, LiveMapLayerKey } from "./liveMapLayerUtils";
import { layerColor } from "./liveMapLayerUtils";

function colorizeByHeight(
  z: number,
  minZ: number,
  maxZ: number,
): [number, number, number] {
  const span = Math.max(0.001, maxZ - minZ);
  const t = THREE.MathUtils.clamp((z - minZ) / span, 0, 1);
  const color = new THREE.Color();
  color.setHSL(0.67 - t * 0.67, 1.0, 0.58);
  return [color.r, color.g, color.b];
}

function colorizeByRange(
  x: number,
  y: number,
  z: number,
): [number, number, number] {
  const distance = Math.sqrt(x * x + y * y + z * z);
  const t = THREE.MathUtils.clamp(distance / 18.0, 0, 1);
  const color = new THREE.Color();
  color.setHSL(0.7 - t * 0.7, 1.0, 0.58);
  return [color.r, color.g, color.b];
}

export type DecodedPointCloud = {
  geometry: THREE.BufferGeometry;
  pointCount: number;
};

export function decodeXyz32(
  buffer: ArrayBuffer,
  options: {
    colorMode: LiveMapColorMode;
    layer: LiveMapLayerKey;
    hasRgb?: boolean;
  },
): DecodedPointCloud {
  const source = new Float32Array(buffer);
  const usableLength = Math.floor(source.length / 3) * 3;
  const pointCount = usableLength / 3;

  const positions = new Float32Array(pointCount * 3);
  const colors = new Float32Array(pointCount * 3);

  let minZ = Number.POSITIVE_INFINITY;
  let maxZ = Number.NEGATIVE_INFINITY;

  for (let index = 0; index < pointCount; index += 1) {
    const z = source[index * 3 + 2];
    if (Number.isFinite(z)) {
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
    }
  }

  if (!Number.isFinite(minZ) || !Number.isFinite(maxZ)) {
    minZ = 0;
    maxZ = 1;
  }

  const [lr, lg, lb] = layerColor(options.layer);

  for (let index = 0; index < pointCount; index += 1) {
    const x = source[index * 3];
    const y = source[index * 3 + 1];
    const z = source[index * 3 + 2];

    positions[index * 3] = x;
    positions[index * 3 + 1] = y;
    positions[index * 3 + 2] = z;

    let rgb: [number, number, number];
    if (options.colorMode === "layer") {
      rgb = [lr, lg, lb];
    } else if (options.colorMode === "distance") {
      rgb = colorizeByRange(x, y, z);
    } else {
      rgb = colorizeByHeight(z, minZ, maxZ);
    }

    colors[index * 3] = rgb[0];
    colors[index * 3 + 1] = rgb[1];
    colors[index * 3 + 2] = rgb[2];
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.computeBoundingSphere();

  return { geometry, pointCount };
}

export function decodeXyzrgb32(
  buffer: ArrayBuffer,
  options: {
    colorMode: LiveMapColorMode;
    layer: LiveMapLayerKey;
  },
): DecodedPointCloud {
  const totalBytes = buffer.byteLength;
  const pointCount = Math.floor(totalBytes / 15);
  const positionBytes = pointCount * 12;

  const positions = new Float32Array(buffer, 0, pointCount * 3);
  const colorBytes = new Uint8Array(buffer, positionBytes, pointCount * 3);

  const outPositions = new Float32Array(pointCount * 3);
  const colors = new Float32Array(pointCount * 3);

  let minZ = Number.POSITIVE_INFINITY;
  let maxZ = Number.NEGATIVE_INFINITY;

  for (let index = 0; index < pointCount; index += 1) {
    const z = positions[index * 3 + 2];
    if (Number.isFinite(z)) {
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
    }
  }

  if (!Number.isFinite(minZ) || !Number.isFinite(maxZ)) {
    minZ = 0;
    maxZ = 1;
  }

  const [lr, lg, lb] = layerColor(options.layer);

  for (let index = 0; index < pointCount; index += 1) {
    const x = positions[index * 3];
    const y = positions[index * 3 + 1];
    const z = positions[index * 3 + 2];

    outPositions[index * 3] = x;
    outPositions[index * 3 + 1] = y;
    outPositions[index * 3 + 2] = z;

    let rgb: [number, number, number];
    if (options.colorMode === "rgb") {
      rgb = [
        colorBytes[index * 3] / 255,
        colorBytes[index * 3 + 1] / 255,
        colorBytes[index * 3 + 2] / 255,
      ];
    } else if (options.colorMode === "layer") {
      rgb = [lr, lg, lb];
    } else if (options.colorMode === "distance") {
      rgb = colorizeByRange(x, y, z);
    } else {
      rgb = colorizeByHeight(z, minZ, maxZ);
    }

    colors[index * 3] = rgb[0];
    colors[index * 3 + 1] = rgb[1];
    colors[index * 3 + 2] = rgb[2];
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(outPositions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.computeBoundingSphere();

  return { geometry, pointCount };
}

export function decodePointCloudBuffer(
  buffer: ArrayBuffer,
  encoding: string | null | undefined,
  options: {
    colorMode: LiveMapColorMode;
    layer: LiveMapLayerKey;
    hasRgb?: boolean;
  },
): DecodedPointCloud {
  if (encoding === "xyzrgb32_v1") {
    return decodeXyzrgb32(buffer, options);
  }

  const floatCount = new Float32Array(buffer).length;
  const maybeRgbFloats = floatCount % 6 === 0 && floatCount >= 6;
  if (maybeRgbFloats && options.colorMode === "rgb" && options.hasRgb) {
    return decodeXyzrgbFloat(buffer, options);
  }

  return decodeXyz32(buffer, options);
}

function decodeXyzrgbFloat(
  buffer: ArrayBuffer,
  options: {
    colorMode: LiveMapColorMode;
    layer: LiveMapLayerKey;
  },
): DecodedPointCloud {
  const source = new Float32Array(buffer);
  const pointCount = Math.floor(source.length / 6);

  const positions = new Float32Array(pointCount * 3);
  const colors = new Float32Array(pointCount * 3);
  const [lr, lg, lb] = layerColor(options.layer);

  for (let index = 0; index < pointCount; index += 1) {
    const base = index * 6;
    positions[index * 3] = source[base];
    positions[index * 3 + 1] = source[base + 1];
    positions[index * 3 + 2] = source[base + 2];

    if (options.colorMode === "rgb") {
      colors[index * 3] = source[base + 3];
      colors[index * 3 + 1] = source[base + 4];
      colors[index * 3 + 2] = source[base + 5];
    } else {
      const rgb =
        options.colorMode === "layer"
          ? [lr, lg, lb]
          : colorizeByHeight(source[base + 2], 0, 1);
      colors[index * 3] = rgb[0];
      colors[index * 3 + 1] = rgb[1];
      colors[index * 3 + 2] = rgb[2];
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.computeBoundingSphere();
  return { geometry, pointCount };
}

export function decimateBufferGeometry(
  geometry: THREE.BufferGeometry,
  maxPoints: number,
): THREE.BufferGeometry {
  const position = geometry.getAttribute("position") as THREE.BufferAttribute | null;
  if (!position || position.count <= maxPoints) {
    return geometry;
  }

  const stride = Math.max(1, Math.ceil(position.count / maxPoints));
  const outCount = Math.ceil(position.count / stride);
  const outPositions = new Float32Array(outCount * 3);
  const colorAttr = geometry.getAttribute("color") as THREE.BufferAttribute | null;
  const outColors = colorAttr ? new Float32Array(outCount * 3) : null;

  let outIndex = 0;
  for (let index = 0; index < position.count; index += stride) {
    outPositions[outIndex * 3] = position.getX(index);
    outPositions[outIndex * 3 + 1] = position.getY(index);
    outPositions[outIndex * 3 + 2] = position.getZ(index);
    if (outColors && colorAttr) {
      outColors[outIndex * 3] = colorAttr.getX(index);
      outColors[outIndex * 3 + 1] = colorAttr.getY(index);
      outColors[outIndex * 3 + 2] = colorAttr.getZ(index);
    }
    outIndex += 1;
  }

  const next = new THREE.BufferGeometry();
  next.setAttribute("position", new THREE.BufferAttribute(outPositions, 3));
  if (outColors) {
    next.setAttribute("color", new THREE.BufferAttribute(outColors, 3));
  }
  next.computeBoundingSphere();
  geometry.dispose();
  return next;
}
