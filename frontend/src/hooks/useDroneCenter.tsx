import { useEffect, useRef, useState } from "react";
import { extractLatLng, type LatLng } from "../lib/extractLatLng";

export function useDroneCenter(telemetry: any) {
  const [droneCenter, setDroneCenter] = useState<LatLng | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const next =
      extractLatLng(telemetry?.position) ||
      extractLatLng(telemetry?.gps) ||
      extractLatLng(telemetry?.home) ||
      extractLatLng(telemetry);

    if (!next) return;

    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }
    rafRef.current = requestAnimationFrame(() => setDroneCenter(next));

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [telemetry]);

  return droneCenter;
}
