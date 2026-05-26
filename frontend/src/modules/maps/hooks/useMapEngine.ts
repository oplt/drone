import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_MISSION_MAP_ENGINE,
  type MissionMapEngine,
} from "../components/MissionMapViewport";

export function dispatchMapEngineChange(engine: MissionMapEngine) {
  window.dispatchEvent(new CustomEvent("mission-map-engine-change", { detail: engine }));
}

export function useMapEngine(initial: MissionMapEngine = DEFAULT_MISSION_MAP_ENGINE) {
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>(initial);

  useEffect(() => {
    const handleEngineChange = (event: Event) => {
      const next = (event as CustomEvent<MissionMapEngine>).detail;
      if (next === "google" || next === "cesium" || next === "leaflet" || next === "maplibre") {
        setMapEngine(next);
      }
    };
    window.addEventListener("mission-map-engine-change", handleEngineChange);
    return () => window.removeEventListener("mission-map-engine-change", handleEngineChange);
  }, []);

  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
    dispatchMapEngineChange(next);
  }, []);

  return { mapEngine, setMapEngine, handleMapEngineChange };
}
