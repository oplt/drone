import { useEffect, useRef, useState } from "react";

export function useDetectionFps(framesProcessed: number | undefined, running: boolean): number | null {
  const sampleRef = useRef<{ frames: number; at: number } | null>(null);
  const [fps, setFps] = useState<number | null>(null);

  useEffect(() => {
    if (!running || framesProcessed == null) {
      sampleRef.current = null;
      setFps(null);
      return;
    }

    const now = Date.now();
    const prev = sampleRef.current;
    if (!prev) {
      sampleRef.current = { frames: framesProcessed, at: now };
      return;
    }

    const elapsedSec = (now - prev.at) / 1000;
    if (elapsedSec < 0.4) return;

    const delta = framesProcessed - prev.frames;
    if (delta >= 0) {
      setFps(Math.max(0, Math.round(delta / elapsedSec)));
    }
    sampleRef.current = { frames: framesProcessed, at: now };
  }, [framesProcessed, running]);

  return fps;
}
