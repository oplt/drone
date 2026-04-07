import { useEffect, useRef, useState } from "react";
import { extractLatLng, type LatLng } from "../lib/extractLatLng";

const INTERPOLATION_DURATION_MS = 300;

export function useDroneCenter(telemetry: any) {
  const [droneCenter, setDroneCenter] = useState<LatLng | null>(null);

  // Track the interpolation state without causing re-renders
  const fromRef = useRef<LatLng | null>(null);
  const targetRef = useRef<LatLng | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const next =
      extractLatLng(telemetry?.position) ||
      extractLatLng(telemetry?.gps) ||
      extractLatLng(telemetry?.home) ||
      extractLatLng(telemetry);

    if (!next) return;

    // Same position — nothing to do
    const prev = targetRef.current;
    if (prev && prev.lat === next.lat && prev.lng === next.lng) return;

    // Cancel any ongoing animation
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    // If no previous position, snap immediately
    if (!prev) {
      fromRef.current = next;
      targetRef.current = next;
      setDroneCenter(next);
      return;
    }

    // Start interpolating from current displayed position toward the new target
    fromRef.current = droneCenter ?? prev;
    targetRef.current = next;
    startTimeRef.current = performance.now();

    const animate = (now: number) => {
      const elapsed = now - (startTimeRef.current ?? now);
      const t = Math.min(elapsed / INTERPOLATION_DURATION_MS, 1);

      // Ease-out cubic for natural deceleration
      const eased = 1 - Math.pow(1 - t, 3);

      const from = fromRef.current!;
      const to = targetRef.current!;
      setDroneCenter({
        lat: from.lat + (to.lat - from.lat) * eased,
        lng: from.lng + (to.lng - from.lng) * eased,
      });

      if (t < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        rafRef.current = null;
        fromRef.current = to;
      }
    };

    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [telemetry]); // eslint-disable-line react-hooks/exhaustive-deps

  return droneCenter;
}
