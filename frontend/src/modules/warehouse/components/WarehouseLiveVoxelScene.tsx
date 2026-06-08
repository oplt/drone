import { Suspense, useMemo, useEffect } from "react";
import Box from "@mui/material/Box";
import * as THREE from "three";
import { Canvas, useLoader, useThree } from "@react-three/fiber";
import { OrbitControls, Line } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import type { CachedLiveMapChunk } from "../hooks/useLiveMapChunkCache";
import { poseToVec3, toRenderChunks } from "../utils/liveMapRenderModel";

export type LiveVoxelLayers = {
  mesh: boolean;
  pointCloud: boolean;
  scanPath: boolean;
  footprint: boolean;
  drone: boolean;
};

function CameraControls() {
  const { camera } = useThree();

  useEffect(() => {
    // ROS/local warehouse convention: Z is up.
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

function decodeXyz32(buffer: ArrayBuffer): THREE.BufferGeometry {
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

    for (let index = 0; index < pointCount; index += 1) {
        const x = source[index * 3];
        const y = source[index * 3 + 1];
        const z = source[index * 3 + 2];

        positions[index * 3] = x;
        positions[index * 3 + 1] = y;
        positions[index * 3 + 2] = z;

        // Use height coloring. Change to colorizeByRange(x, y, z) if you prefer distance coloring.
        const [r, g, b] = colorizeByHeight(z, minZ, maxZ);

        colors[index * 3] = r;
        colors[index * 3 + 1] = g;
        colors[index * 3 + 2] = b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.computeBoundingSphere();

    return geometry;
}

function PointCloudChunk({ chunk }: { chunk: CachedLiveMapChunk }) {
    const geometry = useMemo(() => {
        if (!chunk.arrayBuffer) return null;
        return decodeXyz32(chunk.arrayBuffer);
    }, [chunk.arrayBuffer]);

    useEffect(() => {
        return () => {
            geometry?.dispose();
        };
    }, [geometry]);

    if (!geometry) return null;

    return (
        <points geometry={geometry} frustumCulled={false}>
            <pointsMaterial
                size={0.035}
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
                      }: {
    renderChunk: ReturnType<typeof toRenderChunks>[number];
}) {
    const geometry = useMemo(() => {
        if (!renderChunk.previewPoints.length) return null;

        const pointCount = renderChunk.previewPoints.length;
        const positions = new Float32Array(pointCount * 3);
        const colors = new Float32Array(pointCount * 3);

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

            const [r, g, b] = colorizeByHeight(z, minZ, maxZ);

            colors[index * 3] = r;
            colors[index * 3 + 1] = g;
            colors[index * 3 + 2] = b;
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
                size={0.05}
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

function LiveMapContent({
                          state,
                          layers,
                          cachedChunks,
                        }: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
}) {
  const cachedById = useMemo(() => {
    return new Map(cachedChunks.map((chunk) => [chunk.id, chunk]));
  }, [cachedChunks]);

  const renderChunks = useMemo(() => toRenderChunks(state.chunks), [state.chunks]);

  return (
      <>
        <ambientLight intensity={0.7} />
        <directionalLight position={[4, -6, 8]} intensity={0.8} />

        <GroundGrid visible={layers.footprint} />

        {layers.scanPath && <ScanPath state={state} />}
        {layers.drone && <DroneMarker state={state} />}

        {renderChunks.map((renderChunk) => {
          const cached = cachedById.get(renderChunk.id);

          if (cached?.kind === "point_cloud" && layers.pointCloud) {
            return <PointCloudChunk key={cached.id} chunk={cached} />;
          }

          if (cached?.kind === "mesh" && layers.mesh) {
            return (
                <Suspense key={cached.id} fallback={null}>
                  <MeshChunk chunk={cached} />
                </Suspense>
            );
          }

          if (
              cached &&
              cached.kind !== "point_cloud" &&
              cached.kind !== "mesh" &&
              layers.mesh
          ) {
            return <BoundsChunk key={cached.id} chunk={cached} />;
          }

          // Fallback: render WebSocket preview points while binary chunk is loading.
          if (
              renderChunk.previewPoints.length > 0 &&
              ((renderChunk.kind === "point_cloud" && layers.pointCloud) ||
                  (renderChunk.kind !== "point_cloud" && layers.mesh))
          ) {
            return <PreviewChunk key={renderChunk.id} renderChunk={renderChunk} />;
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
                                        }: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
}) {
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
          />
        </Canvas>
      </Box>
  );
}