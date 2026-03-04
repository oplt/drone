import { Box, FormControlLabel, Switch, ToggleButton, ToggleButtonGroup } from "@mui/material";
import type { CesiumViewMode } from "../../../utils/CesiumMap";

export function CesiumViewControls({
  useCesium,
  onUseCesiumChange,
  viewMode,
  onViewModeChange,
  sx,
}: {
  useCesium: boolean;
  onUseCesiumChange: (next: boolean) => void;
  viewMode: CesiumViewMode;
  onViewModeChange: (mode: CesiumViewMode) => void;
  sx?: any;
}) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", ...sx }}>
      <FormControlLabel
        control={
          <Switch
            checked={useCesium}
            onChange={(e) => onUseCesiumChange(e.target.checked)}
          />
        }
        label={useCesium ? "3D (Cesium)" : "2D (Google)"}
      />

      {useCesium && (
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
