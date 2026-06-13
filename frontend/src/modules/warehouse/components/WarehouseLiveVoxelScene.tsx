import { Suspense, useMemo, useEffect } from "react";
import Box from "@mui/material/Box";
import * as THREE from "three";
import { Canvas, useLoader, useThree } from "@react-three/fiber";
import { OrbitControls, Line } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import type { CachedLiveMapChunk } from "../hooks/useLiveMapChunkCache";
import { poseToVec3, toRenderChunks } from "../utils/liveMapRenderModel";
import {
  decodePointCloudBuffer,
  decimateBufferGeometry,
} from "../utils/liveMapChunkDecoders";
import {
  inferLayerKey,
  type LiveMapColorMode,
  type LiveMapLayerKey,
} from "../utils/liveMapLayerUtils";
import { chunkStateKey } from "../utils/liveMapChunkRetention";

export type LiveVoxelLayers = Record<LiveMapLayerKey, boolean>;

export type LiveVoxelRenderOptions = {
  pointSize: number;
  colorMode: LiveMapColorMode;
  layerPointBudget: Record<LiveMapLayerKey, number>;
};

function CameraControls() {
  const { camera } = useThree();

  useEffect(() => {
    camera.up.set(0, 0, 1);
    camera.lookAt(0, 0, 1.5);
  }, [camera]);

  return (
      <OrbitControls
          makeDefault
          target={[0, 0, 1.5]}
          enableDamping
          dampingFactor={0.08}
      />
  );
}

function GroundGrid({ visible }: { visible: boolean }) {
  if (!visible) return null;

  return (
      <gridHelper
          args={[24, 24]}
          rotation={[Math.PI / 2, 0, 0]}
          position={[0, 0, 0]}
      />
  );
}

function PointCloudChunk({
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

function MeshChunk({ chunk }: { chunk: CachedLiveMapChunk }) {
  if (!chunk.objectUrl) return null;
  return <LoadedMesh objectUrl={chunk.objectUrl} />;
}

function LoadedMesh({ objectUrl }: { objectUrl: string }) {
  const gltf = useLoader(GLTFLoader, objectUrl);
  return <primitive object={gltf.scene} />;
}

function BoundsChunk({ chunk }: { chunk: CachedLiveMapChunk }) {
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

function PreviewChunk({
  renderChunk,
  layer,
  options,
}: {
  renderChunk: ReturnType<typeof toRenderChunks>[number];
  layer: LiveMapLayerKey;
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
  }, [layer, options.colorMode, renderChunk.previewPoints]);

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

function ScanPath({ state }: { state: WarehouseLiveVoxelMapState }) {
  const points = useMemo(
      () =>
          state.scanPath.map(
              (pose) => new THREE.Vector3(pose.x_m, pose.y_m, pose.z_m),
          ),
      [state.scanPath],
  );

  if (points.length < 2) return null;

  return <Line points={points} lineWidth={2} />;
}

function DroneMarker({ state }: { state: WarehouseLiveVoxelMapState }) {
  const [x, y, z] = poseToVec3(state.latestUpdate?.pose ?? null);

  return (
      <group position={[x, y, z]}>
        <mesh>
          <sphereGeometry args={[0.16, 16, 16]} />
          <meshStandardMaterial />
        </mesh>
        <axesHelper args={[0.7]} />
      </group>
  );
}

function layerVisible(
  layer: LiveMapLayerKey,
  layers: LiveVoxelLayers,
): boolean {
  return layers[layer] ?? false;
}

/** Distribute layer point budget evenly across visible layer chunks. */
function distributeLayerPointBudgets(
  chunks: ReturnType<typeof toRenderChunks>,
  metadataByKey: Map<string, { layer: LiveMapLayerKey }>,
  budget: Record<LiveMapLayerKey, number>,
  visibleLayers?: LiveVoxelLayers,
): Map<string, number> {
  const byLayer = new Map<LiveMapLayerKey, string[]>();

  for (const renderChunk of chunks) {
    const meta = metadataByKey.get(renderChunk.stateKey);
    const layer = meta?.layer ?? "mid360LiDAR";
    if (visibleLayers && !layerVisible(layer, visibleLayers)) {
      continue;
    }
    byLayer.set(layer, [...(byLayer.get(layer) ?? []), renderChunk.stateKey]);
  }

  const maxPointsByKey = new Map<string, number>();
  for (const [layer, keys] of byLayer.entries()) {
    const layerBudget = budget[layer] ?? 0;
    if (layerBudget <= 0 || keys.length === 0) continue;
    const perChunk = Math.max(512, Math.floor(layerBudget / keys.length));
    for (const key of keys) {
      maxPointsByKey.set(key, perChunk);
    }
  }

  return maxPointsByKey;
}

function LiveMapContent({
  state,
  layers,
  cachedChunks,
  renderOptions,
  metadataById,
}: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
  renderOptions: LiveVoxelRenderOptions;
  metadataById: Map<string, { layer: LiveMapLayerKey; source?: string | null }>;
}) {
  const cachedByStateKey = useMemo(() => {
    return new Map(
      cachedChunks.map((chunk) => [
        chunkStateKey({
          id: chunk.id,
          source: chunk.source,
          layer: chunk.layer,
        }),
        chunk,
      ]),
    );
  }, [cachedChunks]);

  const renderPlan = useMemo(() => {
    const all = toRenderChunks(state.chunks);
    const maxPointsByKey = distributeLayerPointBudgets(
      all,
      metadataById,
      renderOptions.layerPointBudget,
      layers,
    );

    return all
      .map((renderChunk) => {
        const meta = metadataById.get(renderChunk.stateKey);
        const layer = meta?.layer ?? "mid360LiDAR";
        if (!layerVisible(layer, layers)) {
          return null;
        }
        const cached = cachedByStateKey.get(renderChunk.stateKey);
        if (layer === "nvbloxMesh") {
          return { renderChunk, layer, cached, maxPoints: 1, meta };
        }
        const layerBudget = renderOptions.layerPointBudget[layer] ?? 0;
        if (layerBudget <= 0) {
          return null;
        }
        const maxPoints = maxPointsByKey.get(renderChunk.stateKey) ?? 0;
        return { renderChunk, layer, cached, maxPoints, meta };
      })
      .filter(
        (item): item is NonNullable<typeof item> =>
          item !== null && (item.layer === "nvbloxMesh" || item.maxPoints > 0),
      );
  }, [
    cachedByStateKey,
    layers,
    metadataById,
    renderOptions.layerPointBudget,
    state.chunks,
  ]);

  return (
      <>
        <ambientLight intensity={0.7} />
        <directionalLight position={[4, -6, 8]} intensity={0.8} />

        <GroundGrid visible={layerVisible("grid", layers)} />

        {layerVisible("dronePath", layers) && <ScanPath state={state} />}
        {layerVisible("dronePath", layers) && <DroneMarker state={state} />}

        {renderPlan.map(({ renderChunk, layer, cached, maxPoints }) => {
          if (layer === "nvbloxMesh") {
            if (!layerVisible("nvbloxMesh", layers)) return null;
            if (cached?.kind === "mesh") {
              return (
                  <Suspense key={cached.id} fallback={null}>
                    <MeshChunk chunk={cached} />
                  </Suspense>
              );
            }
            return null;
          }

          const pointLayerVisible =
            (layer === "rgbdColored" && layerVisible("rgbdColored", layers)) ||
            (layer === "mid360LiDAR" && layerVisible("mid360LiDAR", layers)) ||
            (layer === "nvbloxColor" && layerVisible("nvbloxColor", layers)) ||
            (layer === "nvbloxEsdf" && layerVisible("nvbloxEsdf", layers)) ||
            (layer === "nvbloxTsdf" && layerVisible("nvbloxTsdf", layers));

          if (!pointLayerVisible || maxPoints <= 0) return null;

          if (
              cached &&
              (cached.kind === "point_cloud" ||
                cached.kind === "esdf" ||
                cached.kind === "costmap" ||
                cached.kind === "occupancy")
          ) {
            return (
                <PointCloudChunk
                    key={cached.cacheKey ?? cached.id}
                    chunk={cached}
                    layer={layer}
                    options={renderOptions}
                    maxPoints={maxPoints}
                />
            );
          }

          if (cached && cached.kind !== "mesh" && layerVisible("nvbloxEsdf", layers)) {
            return <BoundsChunk key={cached.id} chunk={cached} />;
          }

          if (renderChunk.previewPoints.length > 0) {
            return (
                <PreviewChunk
                    key={renderChunk.id}
                    renderChunk={renderChunk}
                    layer={layer}
                    options={renderOptions}
                />
            );
          }

          return null;
        })}

        <CameraControls />
      </>
  );
}

export function WarehouseLiveVoxelScene({
  state,
  layers,
  cachedChunks,
  renderOptions,
}: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
  renderOptions: LiveVoxelRenderOptions;
}) {
  const metadataById = useMemo(() => {
    const map = new Map<string, { layer: LiveMapLayerKey; source?: string | null }>();
    for (const chunk of state.chunks) {
      map.set(chunkStateKey(chunk), {
        layer: inferLayerKey(chunk),
        source: chunk.source,
      });
    }
    return map;
  }, [state.chunks]);

  return (
      <Box sx={{ height: 520, bgcolor: "#071113", position: "relative" }}>
        <Canvas
            data-testid="warehouse-live-voxel-map"
            camera={{
              position: [8, -12, 7],
              fov: 50,
              near: 0.05,
              far: 500,
            }}
            gl={{
              antialias: true,
              powerPreference: "high-performance",
            }}
        >
          <color attach="background" args={["#071113"]} />
          <LiveMapContent
              state={state}
              layers={layers}
              cachedChunks={cachedChunks}
              renderOptions={renderOptions}
              metadataById={metadataById}
          />
        </Canvas>
      </Box>
  );
}
