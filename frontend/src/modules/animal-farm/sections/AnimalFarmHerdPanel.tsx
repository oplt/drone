import {
  Alert,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { Herd, HerdAlert, LivestockTaskType } from "../types";

type AnimalFarmHerdPanelProps = {
  herds: Herd[];
  selectedHerdId: number | null;
  onSelectedHerdIdChange: (herdId: number) => void;
  loadingHerdOps: boolean;
  collarIdForSearch: string;
  onCollarIdForSearchChange: (value: string) => void;
  onCreateTask: (type: LivestockTaskType) => void;
  onRefreshPositions: () => void;
  onRefreshRisk: () => void;
  herdAlerts: HerdAlert[];
};

export function AnimalFarmHerdPanel({
  herds,
  selectedHerdId,
  onSelectedHerdIdChange,
  loadingHerdOps,
  collarIdForSearch,
  onCollarIdForSearchChange,
  onCreateTask,
  onRefreshPositions,
  onRefreshRisk,
  herdAlerts,
}: AnimalFarmHerdPanelProps) {
  return (
    <Paper sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">Animal Farms</Typography>
        <FormControl size="small" fullWidth>
          <InputLabel id="herd-select-label">Herd</InputLabel>
          <Select
            labelId="herd-select-label"
            label="Herd"
            value={selectedHerdId ?? ""}
            onChange={(e) => onSelectedHerdIdChange(Number(e.target.value))}
          >
            {herds.map((herd) => (
              <MenuItem key={herd.id} value={herd.id}>
                {herd.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Stack direction="row" spacing={0.25} flexWrap="wrap" useFlexGap>
          <ActionIconButton
            variant="plan"
            title="Plan Census"
            color="primary"
            loading={loadingHerdOps}
            disabled={!selectedHerdId}
            onClick={() => onCreateTask("census")}
          />
          <ActionIconButton
            variant="plan"
            title="Plan Herd Sweep"
            color="primary"
            loading={loadingHerdOps}
            disabled={!selectedHerdId}
            onClick={() => onCreateTask("herd_sweep")}
          />
        </Stack>
        <Stack direction="row" spacing={1}>
          <TextField
            variant="filled"
            size="small"
            label="Collar ID (optional)"
            value={collarIdForSearch}
            onChange={(e) => onCollarIdForSearchChange(e.target.value)}
            fullWidth
          />
          <ActionIconButton
            variant="search"
            title="Search"
            loading={loadingHerdOps}
            disabled={!selectedHerdId}
            onClick={() => onCreateTask("search_locate")}
          />
        </Stack>
        <Divider />
        <Stack direction="row" spacing={0.25} alignItems="center">
          <ActionIconButton
            variant="refresh"
            title="Refresh positions"
            disabled={!selectedHerdId}
            onClick={onRefreshPositions}
          />
          <ActionIconButton
            variant="refresh"
            title="Refresh risk"
            disabled={!selectedHerdId}
            onClick={onRefreshRisk}
          />
          {loadingHerdOps && <CircularProgress size={16} />}
        </Stack>
        {herdAlerts.slice(0, 4).map((alert, idx) => (
          <Alert
            key={idx}
            severity={
              alert.severity === "high"
                ? "error"
                : alert.severity === "medium"
                  ? "warning"
                  : "info"
            }
          >
            {alert.type}: {alert.message} ({alert.collar_id})
          </Alert>
        ))}
      </Stack>
    </Paper>
  );
}
