import { useEffect } from "react";
import type { CesiumMapRefs } from "./useCesiumMapRefs";

export function useCesiumUserInteraction(refs: CesiumMapRefs) {
  useEffect(() => {
    const el = refs.hostRef.current;
    if (!el) return;

    const clearTimer = () => {
      if (refs.interactionTimerRef.current != null) {
        clearTimeout(refs.interactionTimerRef.current);
        refs.interactionTimerRef.current = null;
      }
    };

    const startInteraction = () => {
      clearTimer();
      refs.userInteractingRef.current = true;
    };

    const keepAlive = () => {
      if (!refs.userInteractingRef.current) return;
      clearTimer();
      refs.interactionTimerRef.current = setTimeout(() => {
        refs.userInteractingRef.current = false;
      }, 400);
    };

    const endInteraction = () => {
      clearTimer();
      refs.interactionTimerRef.current = setTimeout(() => {
        refs.userInteractingRef.current = false;
      }, 400);
    };

    el.addEventListener("mousedown", startInteraction);
    el.addEventListener("touchstart", startInteraction, { passive: true });
    el.addEventListener("wheel", startInteraction, { passive: true });
    document.addEventListener("mousemove", keepAlive);
    document.addEventListener("touchmove", keepAlive, { passive: true });
    document.addEventListener("mouseup", endInteraction);
    document.addEventListener("touchend", endInteraction);
    el.addEventListener("wheel", endInteraction, { passive: true });

    return () => {
      el.removeEventListener("mousedown", startInteraction);
      el.removeEventListener("touchstart", startInteraction);
      el.removeEventListener("wheel", startInteraction);
      document.removeEventListener("mousemove", keepAlive);
      document.removeEventListener("touchmove", keepAlive);
      document.removeEventListener("mouseup", endInteraction);
      document.removeEventListener("touchend", endInteraction);
      el.removeEventListener("wheel", endInteraction);
      clearTimer();
    };
  }, [refs]);
}
