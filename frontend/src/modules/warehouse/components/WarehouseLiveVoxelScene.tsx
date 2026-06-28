import { Suspense, useMemo, useEffect, useCallback, useRef, useState } from "react";
import Box from "@mui/material/Box";
import * as THREE from "three";
import { Canvas, useLoader, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls, Line } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import type { CachedLiveMapChunk } from "../hooks/useLiveMapChunkCache";
import type { WarehouseMapPlacementViewerProps } from "../hooks/useWarehouseMapPlacement";
import type {
  WarehouseLocalPose,
  WarehouseStructureSummary,
} from "../api/warehouseInspectionApi";
import { poseToVec3, toRenderChunks } from "../utils/liveMapRenderModel";
import {
  scanTargetsForMapMarkers,
  type MapPlacementPoint,
} from "../utils/warehouseMapPlacement";
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
import {
  createWarehouseSceneTransform,
  resolveDisplayedFrame,
  sceneToWarehouseMap,
  WAREHOUSE_MAP_FRAME,
  type WarehouseSceneTransform,
} from "../utils/warehouseSceneCoordinates";

export type LiveVoxelLayers = Record<LiveMapLayerKey, boolean>;

export type LiveVoxelRenderOptions = {
  pointSize: number;
  colorMode: LiveMapColorMode;
  layerPointBudget: Record<LiveMapLayerKey, number>;
};

function CameraControls({
  pickMode,
  focus,
  distance,
  fitKey,
  fitReady,
}: {
  pickMode: boolean;
  focus: [number, number, number];
  distance: number;
  fitKey: string;
  fitReady: boolean;
}) {
  const { camera } = useThree();
  const fittedKeyRef = useRef<string | null>(null);
  const [target, setTarget] = useState<[number, number, number]>(focus);

  useEffect(() => {
    if (!fitReady || fittedKeyRef.current === fitKey) return;

    fittedKeyRef.current = fitKey;
    const nextTarget: [number, number, number] = [...focus];
    setTarget(nextTarget);
    camera.up.set(0, 0, 1);
    camera.position.set(
      focus[0] + distance,
      focus[1] - distance,
      focus[2] + distance * 0.7,
    );
    camera.lookAt(focus[0], focus[1], focus[2]);
    camera.updateProjectionMatrix();
  }, [camera, distance, fitKey, fitReady, focus]);

  return (
      <OrbitControls
          makeDefault
          target={target}
          enableDamping
          dampingFactor={0.08}
          enableRotate={!pickMode}
          enablePan={!pickMode}
          enableZoom
      />
  );
}

function MapPickPlane({
  enabled,
  placementZ,
  onPick,
  transform,
}: {
  enabled: boolean;
  placementZ: number;
  onPick: (point: MapPlacementPoint) => void;
  transform: WarehouseSceneTransform;
}) {
  const handlePointerDown = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!enabled) return;
      event.stopPropagation();
      onPick(sceneToWarehouseMap({
        x_m: event.point.x,
        y_m: event.point.y,
        z_m: event.point.z,
      }, transform));
    },
    [enabled, onPick, transform],
  );

  if (!enabled) return null;

  return (
      <group matrix={transform.warehouseToScene} matrixAutoUpdate={false}>
        <mesh position={[0, 0, placementZ]} onPointerDown={handlePointerDown}>
          <planeGeometry args={[240, 240]} />
          <meshBasicMaterial transparent opacity={0.001} depthWrite={false} />
        </mesh>
      </group>
  );
}

function PlacementMarker({
  point,
  color,
  size = 0.14,
}: {
  point: MapPlacementPoint;
  color: string;
  size?: number;
}) {
  return (
      <mesh position={[point.x_m, point.y_m, point.z_m]}>
        <sphereGeometry args={[size, 16, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.35} />
      </mesh>
  );
}

function ScanPoseMarker({ pose }: { pose: WarehouseLocalPose }) {
  return (
      <group position={[pose.x_m, pose.y_m, pose.z_m]} rotation={[0, 0, ((pose.yaw_deg ?? 0) * Math.PI) / 180]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.12, 0.28, 12]} />
          <meshStandardMaterial color="#38bdf8" emissive="#0ea5e9" emissiveIntensity={0.25} />
        </mesh>
      </group>
  );
}

function ScanTargetMarkers({
  mapPlacement,
}: {
  mapPlacement: WarehouseMapPlacementViewerProps;
}) {
  const savedMarkers = useMemo(
    () => scanTargetsForMapMarkers(mapPlacement.targets),
    [mapPlacement.targets],
  );

  return (
      <>
        {savedMarkers.map(({ id, target, scanPose }) => (
            <group key={id}>
              <PlacementMarker point={target} color="#f97316" size={0.12} />
              <ScanPoseMarker pose={scanPose} />
              <Line
                  points={[
                    new THREE.Vector3(target.x_m, target.y_m, target.z_m),
                    new THREE.Vector3(scanPose.x_m, scanPose.y_m, scanPose.z_m),
                  ]}
                  color="#94a3b8"
                  lineWidth={1}
                  dashed
                  dashSize={0.12}
                  gapSize={0.08}
              />
            </group>
        ))}
        {mapPlacement.draftTarget ? (
            <group>
              <PlacementMarker point={mapPlacement.draftTarget} color="#fde047" size={0.16} />
              {mapPlacement.draftScanPose ? (
                  <>
                    <ScanPoseMarker pose={mapPlacement.draftScanPose} />
                    <Line
                        points={[
                          new THREE.Vector3(
                            mapPlacement.draftTarget.x_m,
                            mapPlacement.draftTarget.y_m,
                            mapPlacement.draftTarget.z_m,
                          ),
                          new THREE.Vector3(
                            mapPlacement.draftScanPose.x_m,
                            mapPlacement.draftScanPose.y_m,
                            mapPlacement.draftScanPose.z_m,
                          ),
                        ]}
                        color="#fde047"
                        lineWidth={2}
                    />
                  </>
              ) : null}
            </group>
        ) : null}
      </>
  );
}

function StructureOverlay({
  structure,
}: {
  structure: WarehouseStructureSummary | null;
}) {
  const overlay = useMemo(() => {
    if (!structure) return null;
    const axisRad = ((structure.axis_deg ?? 0) * Math.PI) / 180;
    const aisles = (structure.aisles ?? []).map((aisle) => {
      const [x0, y0, x1, y1] = aisle.centerline_world;
      const z = ((aisle.z_min ?? 0) + (aisle.z_max ?? 0)) / 2 || aisle.z_min || 0;
      return {
        code: aisle.code,
        points: [
          new THREE.Vector3(x0, y0, structure.floor_z ?? 0),
          new THREE.Vector3(x1, y1, structure.floor_z ?? 0),
        ],
        z,
      };
    });
    const racks = (structure.racks ?? []).map((rack) => {
      const [cx, cy, cz] = rack.center_world;
      const height = Math.max(0.05, (rack.z_max ?? cz) - (rack.z_min ?? cz));
      const midZ = ((rack.z_min ?? cz) + (rack.z_max ?? cz)) / 2 || cz;
      return {
        code: rack.code,
        position: [cx, cy, midZ] as [number, number, number],
        size: [
          Math.max(0.05, rack.length_m),
          Math.max(0.05, rack.depth_m),
          height,
        ] as [number, number, number],
      };
    });
    return { axisRad, aisles, racks };
  }, [structure]);

  if (!overlay) return null;

  return (
    <>
      {overlay.aisles.map((aisle) => (
        <Line
          key={`aisle-${aisle.code}`}
          points={aisle.points}
          color="#22d3ee"
          lineWidth={3}
          dashed
          dashSize={0.4}
          gapSize={0.2}
        />
      ))}
      {overlay.racks.map((rack) => (
        <mesh
          key={`rack-${rack.code}`}
          position={rack.position}
          rotation={[0, 0, overlay.axisRad]}
        >
          <boxGeometry args={rack.size} />
          <meshBasicMaterial
            color="#a855f7"
            wireframe
            transparent
            opacity={0.5}
          />
        </mesh>
      ))}
    </>
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
  mapPlacement,
  structure = null,
}: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
  renderOptions: LiveVoxelRenderOptions;
  metadataById: Map<string, { layer: LiveMapLayerKey; source?: string | null }>;
  mapPlacement?: WarehouseMapPlacementViewerProps | null;
  structure?: WarehouseStructureSummary | null;
}) {
  const cachedByStateKey = useMemo(() => {
    return new Map(
      cachedChunks.map((chunk) => [
        `${chunk.source ?? chunk.layer ?? "unknown"}:${chunk.id}`,
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

  const displayFrameId = useMemo(() => {
    const frames = [
      ...state.chunks.map((chunk) => chunk.frame_id),
      state.latestUpdate?.frame_id,
      ...state.scanPath.map((pose) => pose.frame_id),
    ];
    const hasFrame = frames.some((frame) => Boolean(frame?.trim()));
    return hasFrame ? resolveDisplayedFrame(frames) : WAREHOUSE_MAP_FRAME;
  }, [state.chunks, state.latestUpdate?.frame_id, state.scanPath]);

  const sceneTransform = useMemo(
    () =>
      displayFrameId && mapPlacement?.coordinateFrame
        ? createWarehouseSceneTransform(displayFrameId, mapPlacement.coordinateFrame)
        : null,
    [displayFrameId, mapPlacement?.coordinateFrame],
  );

  const cameraFrame = useMemo(() => {
    const boxes = state.chunks
      .filter((chunk) => layerVisible(inferLayerKey(chunk), layers))
      .map((chunk) => chunk.bbox_local_m)
      .filter(
        (bbox): bbox is [number, number, number, number, number, number] =>
          Array.isArray(bbox) && bbox.length === 6 && bbox.every(Number.isFinite),
      );
    if (boxes.length === 0) {
      return {
        focus: [0, 0, 1.5] as [number, number, number],
        distance: 10,
        ready: false,
      };
    }
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const bbox of boxes) {
      for (let axis = 0; axis < 3; axis += 1) {
        min[axis] = Math.min(min[axis], bbox[axis]);
        max[axis] = Math.max(max[axis], bbox[axis + 3]);
      }
    }
    const focus: [number, number, number] = [
      (min[0] + max[0]) / 2,
      (min[1] + max[1]) / 2,
      (min[2] + max[2]) / 2,
    ];
    const extent = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
    return { focus, distance: Math.max(2.5, extent * 2.5), ready: true };
  }, [layers, state.chunks]);

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
            (layer === "rgbdDepth" && layerVisible("rgbdDepth", layers)) ||
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

        {sceneTransform ? (
          <group matrix={sceneTransform.warehouseToScene} matrixAutoUpdate={false}>
            <StructureOverlay structure={structure} />
            {mapPlacement ? <ScanTargetMarkers mapPlacement={mapPlacement} /> : null}
          </group>
        ) : null}

        {mapPlacement && sceneTransform ? (
            <MapPickPlane
                enabled={mapPlacement.pickMode && !mapPlacement.pickBlockReason}
                placementZ={mapPlacement.placementZ}
                onPick={mapPlacement.onPick}
                transform={sceneTransform}
            />
        ) : null}

        <CameraControls
            pickMode={mapPlacement?.pickMode ?? false}
            focus={cameraFrame.focus}
            distance={cameraFrame.distance}
            fitKey={state.latestUpdate?.flight_id ?? "current-map"}
            fitReady={cameraFrame.ready}
        />
      </>
  );
}

export function WarehouseLiveVoxelScene({
  state,
  layers,
  cachedChunks,
  renderOptions,
  mapPlacement = null,
  structure = null,
}: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
  renderOptions: LiveVoxelRenderOptions;
  mapPlacement?: WarehouseMapPlacementViewerProps | null;
  structure?: WarehouseStructureSummary | null;
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
              mapPlacement={mapPlacement}
              structure={structure}
          />
        </Canvas>
      </Box>
  );
}
