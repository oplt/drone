import { useEffect, useRef, useState } from "react";
import { OrbitControls } from "@react-three/drei";
import { useThree } from "@react-three/fiber";

export function LiveVoxelCameraControls({
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
