import { Suspense, useEffect, useMemo } from "react";
import * as THREE from "three";
import { useLoader } from "@react-three/fiber";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { CachedLiveMapChunk } from "../../../hooks/useLiveMapChunkCache";
import {
  decodePointCloudBuffer,
  decimateBufferGeometry,
} from "../../../utils/liveMapChunkDecoders";
import type { LiveMapLayerKey } from "../../../utils/liveMapLayerUtils";
import { toRenderChunks } from "../../../utils/liveMapRenderModel";
import type { LiveVoxelRenderOptions } from "./liveVoxelSceneTypes";

export function LiveVoxelPointCloudChunk({
  chunk,
  layer,
  options,
  maxPoints,
}: {
  chunk: CachedLiveMapChunk;
  layer: LiveMapLayerKey;
  options: LiveVoxelRenderOptions;
  maxPoints: number;
}) {
  const geometry = useMemo(() => {
    if (!chunk.arrayBuffer) return null;
    const decoded = decodePointCloudBuffer(chunk.arrayBuffer, chunk.encoding, {
      colorMode: options.colorMode,
      layer,
      hasRgb: chunk.has_rgb ?? undefined,
    });
    return decimateBufferGeometry(decoded.geometry, maxPoints);
  }, [
    chunk.arrayBuffer,
    chunk.encoding,
    chunk.has_rgb,
    layer,
    maxPoints,
    options.colorMode,
  ]);

  useEffect(() => {
    return () => {
      geometry?.dispose();
    };
  }, [geometry]);

  if (!geometry) return null;

  return (
    <points geometry={geometry} frustumCulled={false}>
      <pointsMaterial
        size={options.pointSize}
        sizeAttenuation
        vertexColors
        toneMapped={false}
      />
    </points>
  );
}

function LoadedMesh({ objectUrl }: { objectUrl: string }) {
  const gltf = useLoader(GLTFLoader, objectUrl);
  return <primitive object={gltf.scene} />;
}

export function LiveVoxelMeshChunk({ chunk }: { chunk: CachedLiveMapChunk }) {
  if (!chunk.objectUrl) return null;
  return (
    <Suspense fallback={null}>
      <LoadedMesh objectUrl={chunk.objectUrl} />
    </Suspense>
  );
}

export function LiveVoxelBoundsChunk({ chunk }: { chunk: CachedLiveMapChunk }) {
  const bbox = chunk.bbox_local_m;
  if (!bbox) return null;

  const [minX, minY, minZ, maxX, maxY, maxZ] = bbox;
  const center: [number, number, number] = [
    (minX + maxX) / 2,
    (minY + maxY) / 2,
    (minZ + maxZ) / 2,
  ];
  const size: [number, number, number] = [
    Math.max(0.01, maxX - minX),
    Math.max(0.01, maxY - minY),
    Math.max(0.01, maxZ - minZ),
  ];

  return (
    <mesh position={center}>
      <boxGeometry args={size} />
      <meshBasicMaterial wireframe transparent opacity={0.28} />
    </mesh>
  );
}

export function LiveVoxelPreviewChunk({
  renderChunk,
  options,
}: {
  renderChunk: ReturnType<typeof toRenderChunks>[number];
  options: LiveVoxelRenderOptions;
}) {
  const geometry = useMemo(() => {
    if (!renderChunk.previewPoints.length) return null;

    const positions = new Float32Array(renderChunk.previewPoints.length * 3);
    const colors = new Float32Array(renderChunk.previewPoints.length * 3);

    let minZ = Number.POSITIVE_INFINITY;
    let maxZ = Number.NEGATIVE_INFINITY;
    renderChunk.previewPoints.forEach((point) => {
      minZ = Math.min(minZ, point[2]);
      maxZ = Math.max(maxZ, point[2]);
    });
    if (!Number.isFinite(minZ) || !Number.isFinite(maxZ)) {
      minZ = 0;
      maxZ = 1;
    }

    renderChunk.previewPoints.forEach((point, index) => {
      const [x, y, z] = point;
      positions[index * 3] = x;
      positions[index * 3 + 1] = y;
      positions[index * 3 + 2] = z;

      const span = Math.max(0.001, maxZ - minZ);
      const t = THREE.MathUtils.clamp((z - minZ) / span, 0, 1);
      const color = new THREE.Color();
      color.setHSL(0.67 - t * 0.67, 1.0, 0.58);
      colors[index * 3] = color.r;
      colors[index * 3 + 1] = color.g;
      colors[index * 3 + 2] = color.b;
    });

    const next = new THREE.BufferGeometry();
    next.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    next.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    next.computeBoundingSphere();
    return next;
  }, [renderChunk.previewPoints]);

  useEffect(() => {
    return () => {
      geometry?.dispose();
    };
  }, [geometry]);

  if (!geometry) return null;

  return (
    <points geometry={geometry} frustumCulled={false}>
      <pointsMaterial
        size={Math.max(options.pointSize, 0.05)}
        sizeAttenuation
        vertexColors
        toneMapped={false}
      />
    </points>
  );
}
