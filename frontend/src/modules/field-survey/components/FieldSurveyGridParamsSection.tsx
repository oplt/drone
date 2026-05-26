import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import type { GridParams } from "../../mission-planning";
import {
  INFO_INPUT_LABEL_PROPS,
  MAX_GRID_PREVIEW_WAYPOINTS,
} from "../../mission-workflow";

export function FieldSurveyGridParamsSection({
  gridParams,
  setGridParams,
  fieldBorder,
  gridPreview,
  gridPreviewStats,
  previewLegStats,
  gridPreviewTooDense,
  gridPreviewError,
  previewLoading,
}: {
  gridParams: GridParams;
  setGridParams: React.Dispatch<React.SetStateAction<GridParams>>;
  fieldBorder: import("../../fields").LonLat[] | null;
  gridPreview: { lat: number; lon: number }[] | null | undefined;
  gridPreviewStats: { route_m?: number; rows?: number } | null | undefined;
  previewLegStats: { workLegs: number; transitLegs: number } | null;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null | undefined;
  previewLoading: boolean;
}) {
  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Grid Survey Parameters
      </Typography>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              md: "repeat(2, minmax(0, 1fr))",
              xl: "repeat(3, minmax(0, 1fr))",
            },
            gap: 1.5,
            alignItems: "start",
          }}
        >
          <TextField
            variant="filled"
            select
            label={
              <InfoLabel
                label="Pattern mode"
                info="Boustrophedon is a classic lawnmower sweep. Crosshatch adds a second pass."
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            size="small"
            fullWidth
            value={gridParams.pattern_mode}
            onChange={(e) =>
              setGridParams((p) => ({
                ...p,
                pattern_mode: e.target.value as GridParams["pattern_mode"],
              }))
            }
          >
            <MenuItem value="boustrophedon">Boustrophedon (single pass)</MenuItem>
            <MenuItem value="crosshatch">Crosshatch (two passes)</MenuItem>
          </TextField>
          <TextField
            variant="filled"
            select
            label={
              <InfoLabel
                label="Lane strategy"
                info="Serpentine is efficient (classic lawnmower). One-way keeps each lane in the same direction."
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            size="small"
            fullWidth
            value={gridParams.lane_strategy}
            onChange={(e) =>
              setGridParams((p) => ({
                ...p,
                lane_strategy: e.target.value as GridParams["lane_strategy"],
              }))
            }
          >
            <MenuItem value="serpentine">Serpentine (recommended)</MenuItem>
            <MenuItem value="one_way">One-way lanes</MenuItem>
          </TextField>
          <TextField
            variant="filled"
            select
            label={
              <InfoLabel
                label="Start corner"
                info="Choose where lane sequencing starts. Auto keeps the default planner behavior."
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            size="small"
            fullWidth
            value={gridParams.start_corner}
            onChange={(e) =>
              setGridParams((p) => ({
                ...p,
                start_corner: e.target.value as GridParams["start_corner"],
              }))
            }
          >
            <MenuItem value="auto">Auto</MenuItem>
            <MenuItem value="sw">South-West</MenuItem>
            <MenuItem value="se">South-East</MenuItem>
            <MenuItem value="nw">North-West</MenuItem>
            <MenuItem value="ne">North-East</MenuItem>
          </TextField>
          <TextField
            variant="filled"
            label="Row spacing (m)"
            type="number"
            size="small"
            fullWidth
            value={gridParams.row_spacing_m}
            onChange={(e) => {
              const value = Number(e.target.value);
              if (!Number.isFinite(value)) return;
              setGridParams((p) => ({
                ...p,
                row_spacing_m: Math.max(1, value),
              }));
            }}
            inputProps={{ min: 1, max: 200, step: 0.5 }}
          />
          <TextField
            variant="filled"
            label={
              <InfoLabel
                label="Row stride (every Nth line)"
                info="1 uses every line. 2 flies every second line (wider effective spacing)."
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            type="number"
            size="small"
            fullWidth
            value={gridParams.row_stride}
            onChange={(e) => {
              const value = Number(e.target.value);
              if (!Number.isFinite(value)) return;
              setGridParams((p) => ({
                ...p,
                row_stride: Math.min(20, Math.max(1, Math.round(value))),
              }));
            }}
            inputProps={{ min: 1, max: 20, step: 1 }}
          />
          <TextField
            variant="filled"
            label={
              <InfoLabel
                label="Row phase offset (m)"
                info="Shifts line placement to align passes with crop rows."
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            type="number"
            size="small"
            fullWidth
            value={gridParams.row_phase_m}
            onChange={(e) => {
              const value = Number(e.target.value);
              if (!Number.isFinite(value)) return;
              setGridParams((p) => ({
                ...p,
                row_phase_m: Math.max(0, value),
              }));
            }}
            inputProps={{ min: 0, max: 500, step: 0.5 }}
          />
          <TextField
            variant="filled"
            label={
              <InfoLabel
                label="Grid angle (°, blank = auto)"
                info="Leave blank to auto-align with terrain."
              />
            }
            InputLabelProps={INFO_INPUT_LABEL_PROPS}
            type="number"
            size="small"
            fullWidth
            value={gridParams.grid_angle_deg ?? ""}
            onChange={(e) =>
              setGridParams((p) => ({
                ...p,
                grid_angle_deg:
                  e.target.value === "" ? null : Number(e.target.value),
              }))
            }
            inputProps={{ min: 0, max: 179, step: 1 }}
          />
          {gridParams.pattern_mode === "crosshatch" && (
            <TextField
              variant="filled"
              label={
                <InfoLabel
                  label="Crosshatch angle offset (°)"
                  info="90° gives an orthogonal second pass."
                />
              }
              InputLabelProps={INFO_INPUT_LABEL_PROPS}
              type="number"
              size="small"
              fullWidth
              value={gridParams.crosshatch_angle_offset_deg}
              onChange={(e) => {
                const value = Number(e.target.value);
                if (!Number.isFinite(value)) return;
                setGridParams((p) => ({
                  ...p,
                  crosshatch_angle_offset_deg: Math.min(179, Math.max(1, value)),
                }));
              }}
              inputProps={{ min: 1, max: 179, step: 1 }}
            />
          )}
          <TextField
            variant="filled"
            label="Safety inset (m)"
            type="number"
            size="small"
            fullWidth
            value={gridParams.safety_inset_m}
            onChange={(e) =>
              setGridParams((p) => ({
                ...p,
                safety_inset_m: Math.max(0, Number(e.target.value)),
              }))
            }
            inputProps={{ min: 0, max: 20, step: 0.5 }}
          />
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={gridParams.slope_aware}
                onChange={(e) =>
                  setGridParams((p) => ({
                    ...p,
                    slope_aware: e.target.checked,
                  }))
                }
              />
            }
            label={<Typography variant="caption">Slope-aware angle</Typography>}
          />
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={gridParams.terrain_follow}
                onChange={(e) =>
                  setGridParams((p) => ({
                    ...p,
                    terrain_follow: e.target.checked,
                  }))
                }
              />
            }
            label={
              <Typography variant="caption">Terrain following (AGL)</Typography>
            }
          />
          {gridParams.terrain_follow && (
            <TextField
              variant="filled"
              label="AGL height (m)"
              type="number"
              size="small"
              fullWidth
              value={gridParams.agl_m}
              onChange={(e) =>
                setGridParams((p) => ({
                  ...p,
                  agl_m: Math.max(1, Number(e.target.value)),
                }))
              }
              inputProps={{ min: 1, max: 200, step: 1 }}
            />
          )}
          {!fieldBorder && (
            <Alert severity="info" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
              Draw or select a field polygon above to generate a grid preview.
            </Alert>
          )}
          {fieldBorder && gridPreview && (
            <Stack
              direction="row"
              spacing={1}
              sx={{ flexWrap: "wrap", rowGap: 1, gridColumn: "1 / -1" }}
            >
              <Chip
                size="small"
                color="success"
                label={`${gridPreview.length} waypoints previewed`}
              />
              {typeof gridPreviewStats?.route_m === "number" && (
                <Chip
                  size="small"
                  color="primary"
                  variant="outlined"
                  label={`Route ${gridPreviewStats.route_m.toFixed(1)} m`}
                />
              )}
              {typeof gridPreviewStats?.rows === "number" && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`${gridPreviewStats.rows} rows`}
                />
              )}
              {previewLegStats && (
                <>
                  <Chip
                    size="small"
                    color="primary"
                    variant="outlined"
                    label={`${previewLegStats.workLegs} work legs`}
                  />
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`${previewLegStats.transitLegs} transit legs`}
                  />
                </>
              )}
            </Stack>
          )}
          {gridPreviewTooDense && (
            <Alert severity="warning" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
              Grid preview is too dense ({gridPreview?.length}/
              {MAX_GRID_PREVIEW_WAYPOINTS} waypoints). Increase row spacing or row
              stride before starting the survey.
            </Alert>
          )}
          {gridPreviewError && (
            <Alert severity="warning" sx={{ py: 0.5, gridColumn: "1 / -1" }}>
              {gridPreviewError}
            </Alert>
          )}
          {previewLoading && (
            <Box
              sx={{
                display: "flex",
                justifyContent: "center",
                gridColumn: "1 / -1",
              }}
            >
              <CircularProgress size={20} />
            </Box>
          )}
        </Box>
      </Paper>
    </Box>
  );
}
