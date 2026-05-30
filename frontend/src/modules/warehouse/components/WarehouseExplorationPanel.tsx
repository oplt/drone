import { useCallback, useEffect, useState } from "react";
import ExploreRoundedIcon from "@mui/icons-material/ExploreRounded";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  InputAdornment,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
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
  warehouseName?: string;
  getToken: () => string | null;
  onLaunch: (launch: WarehouseMissionLaunchResponse) => void;
  onError: (message: string, error?: unknown) => void;
};

const DEFAULT_PROFILE: WarehouseExplorationProfile = {
  max_radius_m: 80,
  min_clearance_m: 1,
  max_frontier_candidates: 8,
  return_battery_reserve_pct: 30,
  max_duration_s: 900,
};

const EXPLORATION_FIELD_SX = {
  minWidth: 0,
  "& .MuiInputBase-input": { px: 0.75, py: 0.75 },
  "& .MuiInputAdornment-root": { ml: 0, mr: 0.25 },
  "& .MuiInputAdornment-root .MuiTypography-root": { fontSize: "0.7rem" },
  "& .MuiInputLabel-root": { fontSize: "0.75rem" },
} as const;

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

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, borderColor: "divider" }}>
      <Stack spacing={1.25}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle1">
            <InfoLabel
              label="Exploration"
              info="Frontier mode uses the ROS nvblox ESDF map and returns before reserve battery."
            />
          </Typography>
          {loading && <CircularProgress size={16} />}
        </Stack>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "repeat(5, minmax(56px, 1fr))",
            gap: 0.75,
            minWidth: 0,
          }}
        >
          {EXPLORATION_FIELDS.map((field) => (
            <TextField
              key={field.key}
              size="small"
              fullWidth
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
        {selectedDockId == null && (
          <Alert severity="warning">Exploration needs a dock anchor for return.</Alert>
        )}
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            size="small"
            startIcon={<SaveOutlinedIcon />}
            disabled={saving}
            onClick={saveProfile}
          >
            Save Profile
          </Button>
          <Button
            variant="contained"
            size="small"
            startIcon={<ExploreRoundedIcon />}
            disabled={starting || warehouseMapId == null || selectedDockId == null}
            onClick={launchExploration}
          >
            {starting ? "Starting..." : "Start Exploration"}
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
