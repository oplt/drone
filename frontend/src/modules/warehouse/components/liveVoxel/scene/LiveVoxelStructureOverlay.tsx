import { useMemo } from "react";
import * as THREE from "three";
import { Line } from "@react-three/drei";
import type { WarehouseStructureSummary } from "../../../api/warehouseInspectionApi";

export function LiveVoxelStructureOverlay({
  structure,
}: {
  structure: WarehouseStructureSummary | null;
}) {
  const overlay = useMemo(() => {
    if (!structure) return null;
    const axisRad = ((structure.axis_deg ?? 0) * Math.PI) / 180;
    const aisles = (structure.aisles ?? []).map((aisle) => {
      const [x0, y0, x1, y1] = aisle.centerline_world;
      return {
        code: aisle.code,
        points: [
          new THREE.Vector3(x0, y0, structure.floor_z ?? 0),
          new THREE.Vector3(x1, y1, structure.floor_z ?? 0),
        ],
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
          <meshBasicMaterial color="#a855f7" wireframe transparent opacity={0.5} />
        </mesh>
      ))}
    </>
  );
}

export function LiveVoxelGroundGrid({ visible }: { visible: boolean }) {
  if (!visible) return null;

  return (
    <gridHelper args={[24, 24]} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, 0]} />
  );
}
