import { useMemo } from "react";
import * as THREE from "three";
import { Line } from "@react-three/drei";
import type { WarehouseLiveVoxelMapState } from "../../../hooks/useWarehouseLiveVoxelMap";
import { poseToVec3 } from "../../../utils/liveMapRenderModel";

export function LiveVoxelScanPath({ state }: { state: WarehouseLiveVoxelMapState }) {
  const points = useMemo(
    () => state.scanPath.map((pose) => new THREE.Vector3(pose.x_m, pose.y_m, pose.z_m)),
    [state.scanPath],
  );

  if (points.length < 2) return null;

  return <Line points={points} lineWidth={2} />;
}

export function LiveVoxelDroneMarker({ state }: { state: WarehouseLiveVoxelMapState }) {
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
