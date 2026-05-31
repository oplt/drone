import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  CircularProgress,
  IconButton,
  InputAdornment,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import SaveIcon from "@mui/icons-material/Save";
import FlightTakeoffIcon from "@mui/icons-material/FlightTakeoff";
import InfoLabel from "../../../shared/ui/InfoLabel";
import {
  fetchWarehouseExplorationProfile,
  startWarehouseExploration,
  updateWarehouseExplorationProfile,
} from "../api/warehouseMissionsApi";
import type {
  WarehouseExplorationProfile,
  WarehouseMissionLaunchResponse,
} from "../types/missions";

type Props = {
  warehouseMapId: number | null;
  selectedDockId: number | null;
  warehouseName?: string | null;
  getToken: () => string | null;
  onLaunch: (launch: WarehouseMissionLaunchResponse) => void;
  onError: (message: string, error?: unknown) => void;
  embedded?: boolean;
  warehousePreflightPassed?: boolean;
};

const DEFAULT_PROFILE: WarehouseExplorationProfile = {
  max_radius_m: 80,
  min_clearance_m: 1,
  max_frontier_candidates: 8,
  return_battery_reserve_pct: 30,
  max_duration_s: 900,
};

const CLASSIC_FILLED_INPUT_SX = {
  "& .MuiFilledInput-root": {
    border: "none !important",
    boxShadow: "none",
    backgroundColor: "grey.200",
    "&:before, &:after": { display: "none" },
    "&:hover": {
      border: "none !important",
      backgroundColor: "grey.300",
    },
    "&.Mui-focused": {
      border: "none !important",
      backgroundColor: "grey.300",
    },
  },
  '[data-mui-color-scheme="dark"] & .MuiFilledInput-root': {
    backgroundColor: "grey.800",
    "&:hover": { backgroundColor: "grey.700" },
    "&.Mui-focused": { backgroundColor: "grey.700" },
  },
} as const;

/** 40% smaller than prior exploration field size (5.2rem → 3.12rem). */
const EXPLORATION_FIELD_WIDTH = "3.12rem";

const EXPLORATION_FIELD_SX = {
  flex: "0 0 auto",
  width: EXPLORATION_FIELD_WIDTH,
  maxWidth: EXPLORATION_FIELD_WIDTH,
  ...CLASSIC_FILLED_INPUT_SX,
  "& .MuiFilledInput-root": {
    ...CLASSIC_FILLED_INPUT_SX["& .MuiFilledInput-root"],
    minHeight: "1.65rem",
    paddingTop: 0,
    paddingBottom: 0,
  },
  "[data-mui-color-scheme=\"dark\"] & .MuiFilledInput-root": CLASSIC_FILLED_INPUT_SX[
    '[data-mui-color-scheme="dark"] & .MuiFilledInput-root'
  ],
  "& .MuiInputBase-root": { fontSize: "0.65rem" },
  "& .MuiFilledInput-input": {
    px: 0.45,
    py: 0.25,
    pt: 0.75,
    pb: 0.25,
    textAlign: "right",
    MozAppearance: "textfield",
    "&::-webkit-outer-spin-button, &::-webkit-inner-spin-button": {
      WebkitAppearance: "none",
      margin: 0,
    },
  },
  "& .MuiInputAdornment-root": { ml: 0, mr: 0.15 },
  "& .MuiInputAdornment-root .MuiTypography-root": { fontSize: "0.6rem" },
  "& .MuiInputLabel-root": {
    fontSize: "0.6rem",
    transform: "translate(8px, 6px) scale(1)",
  },
  "& .MuiInputLabel-shrink": {
    transform: "translate(8px, -6px) scale(0.72)",
  },
} as const;

const EMBEDDED_EXPLORATION_FIELD_SX = EXPLORATION_FIELD_SX;

const EXPLORATION_FIELDS = [
  {
    key: "max_radius_m" as const,
    label: "Radius",
    adornment: "m",
  },
  {
    key: "min_clearance_m" as const,
    label: "Clearance",
    adornment: "m",
  },
  {
    key: "max_frontier_candidates" as const,
    label: "Frontiers",
    adornment: null,
  },
  {
    key: "return_battery_reserve_pct" as const,
    label: "Reserve",
    adornment: "%",
  },
  {
    key: "max_duration_s" as const,
    label: "Duration",
    adornment: "s",
  },
];

export function WarehouseExplorationPanel({
  warehouseMapId,
  selectedDockId,
  warehouseName,
  getToken,
  onLaunch,
  onError,
  embedded = false,
  warehousePreflightPassed = false,
}: Props) {
  const [profile, setProfile] = useState<WarehouseExplorationProfile>(DEFAULT_PROFILE);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);

  const loadProfile = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      setProfile(await fetchWarehouseExplorationProfile(token));
    } catch (error) {
      onError("Exploration profile could not be loaded.", error);
    } finally {
      setLoading(false);
    }
  }, [getToken, onError]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const updateNumber = (key: keyof WarehouseExplorationProfile, value: string) => {
    setProfile((current) => ({ ...current, [key]: Number(value) }));
  };

  const saveProfile = async () => {
    const token = getToken();
    if (!token) return;
    setSaving(true);
    try {
      setProfile(await updateWarehouseExplorationProfile(profile, token));
    } catch (error) {
      onError("Exploration profile could not be saved.", error);
    } finally {
      setSaving(false);
    }
  };

  const launchExploration = async () => {
    const token = getToken();
    if (!token || warehouseMapId == null) return;
    if (selectedDockId == null) {
      onError("Select a dock station before starting exploration.");
      return;
    }
    setStarting(true);
    try {
      const launch = await startWarehouseExploration(
        {
          warehouse_map_id: warehouseMapId,
          dock_id: selectedDockId,
          mission_name: `Warehouse Exploration${warehouseName ? ` - ${warehouseName}` : ""}`,
          hover_alt_m: 2.5,
          exploration: {
            max_mission_time_s: profile.max_duration_s,
            max_exploration_radius_m: profile.max_radius_m,
            minimum_corridor_clearance_m: profile.min_clearance_m,
            obstacle_clearance_m: profile.min_clearance_m,
            max_frontier_candidates: profile.max_frontier_candidates,
            battery_return_reserve_pct: profile.return_battery_reserve_pct,
          },
        },
        token,
      );
      onLaunch(launch);
    } catch (error) {
      onError("Warehouse exploration could not be started.", error);
    } finally {
      setStarting(false);
    }
  };

  const content = (
    <Stack spacing={1.25}>
      {!embedded && (
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle1">
            <InfoLabel
              label="Exploration"
              info="Frontier mode uses the ROS nvblox ESDF map and returns before reserve battery."
            />
          </Typography>
          {loading && <CircularProgress size={16} />}
        </Stack>
      )}
      {embedded && loading && (
        <Stack direction="row" justifyContent="flex-end">
          <CircularProgress size={16} />
        </Stack>
      )}
        {embedded ? (
          <Stack direction="row" spacing={0.5} alignItems="flex-start" sx={{ minWidth: 0 }}>
            {EXPLORATION_FIELDS.map((field) => (
              <TextField
                variant="filled"
                key={field.key}
                size="small"
                type="number"
                label={field.label}
                value={profile[field.key]}
                sx={EMBEDDED_EXPLORATION_FIELD_SX}
                InputProps={
                  field.adornment
                    ? {
                        endAdornment: (
                          <InputAdornment position="end">{field.adornment}</InputAdornment>
                        ),
                      }
                    : undefined
                }
                onChange={(event) => updateNumber(field.key, event.target.value)}
              />
            ))}
            <Stack direction="row" spacing={0.25} sx={{ flexShrink: 0, pt: 0.35 }}>
              <Tooltip title="Save Profile">
                <span>
                  <IconButton
                    size="small"
                    aria-label="Save Profile"
                    disabled={saving}
                    onClick={() => {
                      void saveProfile();
                    }}
                  >
                    {saving ? <CircularProgress size={18} /> : <SaveIcon fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title={starting ? "Starting…" : "Start Exploration"}>
                <span>
                  <IconButton
                    size="small"
                    color="primary"
                    aria-label="Start Exploration"
                    disabled={
                      !warehousePreflightPassed ||
                      warehouseMapId == null ||
                      selectedDockId == null ||
                      starting
                    }
                    onClick={() => {
                      void launchExploration();
                    }}
                  >
                    {starting ? (
                      <CircularProgress size={18} color="inherit" />
                    ) : (
                      <FlightTakeoffIcon fontSize="small" />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          </Stack>
        ) : (
          <>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: `repeat(5, ${EXPLORATION_FIELD_WIDTH})`,
                gap: 0.5,
                minWidth: 0,
                width: "fit-content",
                maxWidth: "100%",
              }}
            >
              {EXPLORATION_FIELDS.map((field) => (
                <TextField
                  variant="filled"
                  key={field.key}
                  size="small"
                  type="number"
                  label={field.label}
                  value={profile[field.key]}
                  sx={EXPLORATION_FIELD_SX}
                  InputProps={
                    field.adornment
                      ? {
                          endAdornment: (
                            <InputAdornment position="end">{field.adornment}</InputAdornment>
                          ),
                        }
                      : undefined
                  }
                  onChange={(event) => updateNumber(field.key, event.target.value)}
                />
              ))}
            </Box>
            <Stack direction="row" spacing={0.25}>
              <Tooltip title="Save Profile">
                <span>
                  <IconButton
                    size="small"
                    aria-label="Save Profile"
                    disabled={saving}
                    onClick={() => {
                      void saveProfile();
                    }}
                  >
                    {saving ? <CircularProgress size={18} /> : <SaveIcon fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title={starting ? "Starting…" : "Start Exploration"}>
                <span>
                  <IconButton
                    size="small"
                    color="primary"
                    aria-label="Start Exploration"
                    disabled={
                      !warehousePreflightPassed ||
                      warehouseMapId == null ||
                      selectedDockId == null ||
                      starting
                    }
                    onClick={() => {
                      void launchExploration();
                    }}
                  >
                    {starting ? (
                      <CircularProgress size={18} color="inherit" />
                    ) : (
                      <FlightTakeoffIcon fontSize="small" />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          </>
        )}
        {selectedDockId == null && (
          <Alert severity="warning">Exploration needs a dock anchor for return.</Alert>
        )}
        {!warehousePreflightPassed && (
          <Alert severity="warning">Run Warehouse Preflight above before starting exploration.</Alert>
        )}
      </Stack>
  );

  if (embedded) return content;

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: "divider" }}>
      {content}
    </Paper>
  );
}
