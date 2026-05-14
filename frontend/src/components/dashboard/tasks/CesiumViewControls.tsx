import {
  Box,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import { useEffect, useState } from "react";
import type { CesiumViewMode } from "../../../utils/CesiumMap";
import type { MissionMapEngine } from "./MissionMapViewport";

export function CesiumViewControls({
  useCesium,
  onUseCesiumChange,
  mapEngine,
  onMapEngineChange,
  viewMode,
  onViewModeChange,
  sx,
}: {
  useCesium: boolean;
  onUseCesiumChange: (next: boolean) => void;
  mapEngine?: MissionMapEngine;
  onMapEngineChange?: (next: MissionMapEngine) => void;
  viewMode: CesiumViewMode;
  onViewModeChange: (mode: CesiumViewMode) => void;
  sx?: any;
}) {
  const [localEngine, setLocalEngine] = useState<MissionMapEngine>(
    useCesium ? "cesium" : "google",
  );
  const selectedEngine = mapEngine ?? localEngine;

  useEffect(() => {
    if (mapEngine) return;
    if (useCesium) {
      setLocalEngine("cesium");
      return;
    }
    setLocalEngine((current) => (current === "cesium" ? "google" : current));
  }, [mapEngine, useCesium]);

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", ...sx }}>
      <FormControl size="small">
        <RadioGroup
          row
          aria-label="Map engine"
          value={selectedEngine}
          onChange={(event) => {
            const next = event.target.value as MissionMapEngine;
            setLocalEngine(next);
            if (onMapEngineChange) {
              onMapEngineChange(next);
            } else {
              onUseCesiumChange(next === "cesium");
            }
            window.dispatchEvent(
              new CustomEvent<MissionMapEngine>("mission-map-engine-change", {
                detail: next,
              }),
            );
          }}
        >
          <FormControlLabel value="google" control={<Radio size="small" />} label="Google" />
          <FormControlLabel value="cesium" control={<Radio size="small" />} label="Cesium" />
          <FormControlLabel value="leaflet" control={<Radio size="small" />} label="Leaflet" />
          <FormControlLabel value="maplibre" control={<Radio size="small" />} label="MapLibre" />
        </RadioGroup>
      </FormControl>

      {selectedEngine === "cesium" && (
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          size="small"
          onChange={(_, v) => {
            if (!v) return;
            onViewModeChange(v);
          }}
          aria-label="Cesium view mode"
        >
          <ToggleButton value="top" aria-label="Top view">
            Top
          </ToggleButton>
          <ToggleButton value="tilted" aria-label="Tilted view">
            Tilted
          </ToggleButton>
          <ToggleButton value="follow" aria-label="Follow drone">
            Follow
          </ToggleButton>
          <ToggleButton value="fpv" aria-label="FPV view">
            FPV
          </ToggleButton>
          <ToggleButton value="orbit" aria-label="Orbit view">
            Orbit
          </ToggleButton>
        </ToggleButtonGroup>
      )}
    </Box>
  );
}
