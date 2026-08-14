import { useCallback, useMemo } from "react";
import * as THREE from "three";
import { Line } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import type { WarehouseMapPlacementViewerProps } from "../../../hooks/useWarehouseMapPlacement";
import {
  sceneToWarehouseMap,
  type WarehouseSceneTransform,
} from "../../../utils/warehouseSceneCoordinates";
import {
  scanTargetsForMapMarkers,
  type MapPlacementPoint,
} from "../../../utils/warehouseMapPlacement";
import type { WarehouseLocalPose } from "../../../api/warehouseInspectionApi";

export function LiveVoxelMapPickPlane({
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
      onPick(
        sceneToWarehouseMap(
          {
            x_m: event.point.x,
            y_m: event.point.y,
            z_m: event.point.z,
          },
          transform,
        ),
      );
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
    <group
      position={[pose.x_m, pose.y_m, pose.z_m]}
      rotation={[0, 0, ((pose.yaw_deg ?? 0) * Math.PI) / 180]}
    >
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.12, 0.28, 12]} />
        <meshStandardMaterial color="#38bdf8" emissive="#0ea5e9" emissiveIntensity={0.25} />
      </mesh>
    </group>
  );
}

export function LiveVoxelScanTargetMarkers({
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
