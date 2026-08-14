import { useCallback, useState } from "react";
import {
  DEFAULT_MISSION_MAP_ENGINE,
  type CesiumViewMode,
  type MissionMapEngine,
} from "../../maps";

export function useAnimalFarmMapEngine() {
  const [useCesium, setUseCesium] = useState(false);
  const [mapEngine, setMapEngine] = useState<MissionMapEngine>(DEFAULT_MISSION_MAP_ENGINE);
  const [cesiumViewMode, setCesiumViewMode] = useState<CesiumViewMode>("tilted");

  const handleMapEngineChange = useCallback((next: MissionMapEngine) => {
    setMapEngine(next);
    setUseCesium(next === "cesium");
  }, []);

  return {
    useCesium,
    mapEngine,
    cesiumViewMode,
    setCesiumViewMode,
    handleMapEngineChange,
  };
}
