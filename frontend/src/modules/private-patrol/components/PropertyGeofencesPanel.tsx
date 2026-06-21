import { useEffect, useState } from "react";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import SaveIcon from "@mui/icons-material/Save";
import UpdateIcon from "@mui/icons-material/Update";
import {
  Box,
  Chip,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { BorderMetrics, FieldFeature } from "../../fields";

type PropertyGeofencesPanelProps = {
  fields: FieldFeature[];
  selectedFieldId: number | null;
  selectedField: FieldFeature | null;
  loadingFields: boolean;
  deletingField: boolean;
  fieldName: string;
  fieldBorder: { length: number } | null;
  metrics: BorderMetrics | null;
  savingField: boolean;
  onSelectField: (fieldId: number | null) => void;
  onRefresh: () => void;
  onFocusSelected: () => void;
  onDeleteSelected: () => void;
  onFieldNameChange: (name: string) => void;
  onStartNew: () => void;
  onSave: () => void | Promise<void>;
  onUpdate: () => void | Promise<void>;
};

export function PropertyGeofencesPanel({
  fields,
  selectedFieldId,
  selectedField,
  loadingFields,
  deletingField,
  fieldName,
  fieldBorder,
  metrics,
  savingField,
  onSelectField,
  onRefresh,
  onFocusSelected,
  onDeleteSelected,
  onFieldNameChange,
  onStartNew,
  onSave,
  onUpdate,
}: PropertyGeofencesPanelProps) {
  const [creatingNew, setCreatingNew] = useState(false);

  useEffect(() => {
    if (selectedFieldId != null) {
      setCreatingNew(false);
    }
  }, [selectedFieldId]);

  const hasPolygon = Boolean(fieldBorder && fieldBorder.length >= 3);
  const canSaveNew = creatingNew && hasPolygon && fieldName.trim().length > 0;
  const canUpdate = !creatingNew && selectedFieldId != null && hasPolygon && fieldName.trim().length > 0;

  function handleStartNew() {
    setCreatingNew(true);
    onStartNew();
  }

  function handleSelectField(fieldId: number | null) {
    setCreatingNew(false);
    onSelectField(fieldId);
  }

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: 2,
        minWidth: 0,
        height: "100%",
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        <InfoLabel
          label="Property Geofences"
          info="Select a saved geofence, or click + to draw a new polygon on the map, type its name here, and save."
        />
      </Typography>

      <Stack spacing={1.25}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={0.75}
          alignItems={{ xs: "stretch", sm: "flex-start" }}
          sx={{ minWidth: 0, width: "100%" }}
        >
          {creatingNew ? (
            <TextField
              variant="filled"
              size="small"
              fullWidth
              autoFocus
              label="Property geofences"
              placeholder="Enter property name"
              value={fieldName}
              onChange={(e) => onFieldNameChange(e.target.value)}
              helperText="Draw a polygon on the map, then save."
              sx={{ flex: "1 1 0", minWidth: 0 }}
            />
          ) : (
            <TextField
              variant="filled"
              select
              size="small"
              fullWidth
              label="Property geofences"
              value={selectedFieldId == null ? "" : String(selectedFieldId)}
              onChange={(e) => {
                const raw = e.target.value;
                handleSelectField(raw ? Number(raw) : null);
              }}
              helperText={
                selectedField ? `Selected: ${selectedField.name} (#${selectedField.id})` : undefined
              }
              sx={{ flex: "1 1 0", minWidth: 0 }}
            >
              <MenuItem value="">None</MenuItem>
              {fields.map((field) => (
                <MenuItem key={field.id} value={String(field.id)}>
                  {field.name} (#{field.id})
                </MenuItem>
              ))}
            </TextField>
          )}

          <Stack
            direction="row"
            spacing={0.25}
            alignItems="center"
            sx={{
              flex: "0 0 auto",
              pt: { xs: 0, sm: 0.5 },
              "& .MuiIconButton-root": {
                width: 32,
                height: 32,
                p: 0.5,
              },
            }}
          >
            {creatingNew && (
              <Tooltip title="Save property geofence">
                <span>
                  <IconButton
                    size="small"
                    color="primary"
                    disabled={savingField || !canSaveNew}
                    onClick={() => void onSave()}
                    aria-label="Save property geofence"
                  >
                    <SaveIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            )}
            {canUpdate && (
              <Tooltip title="Update property geofence">
                <span>
                  <IconButton
                    size="small"
                    color="primary"
                    disabled={savingField}
                    onClick={() => void onUpdate()}
                    aria-label="Update property geofence"
                  >
                    <UpdateIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            )}
            <Tooltip title="New property geofence">
              <IconButton
                size="small"
                color={creatingNew ? "primary" : "default"}
                onClick={handleStartNew}
                aria-label="New property geofence"
              >
                <AddRoundedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <ActionIconButton
              variant="refresh"
              title="Refresh property geofences"
              loading={loadingFields}
              onClick={onRefresh}
            />
            <ActionIconButton
              variant="focus"
              title="Focus selected geofence"
              disabled={!selectedField || creatingNew}
              onClick={onFocusSelected}
            />
            <ActionIconButton
              variant="delete"
              title="Delete selected geofence"
              color="error"
              loading={deletingField}
              disabled={!selectedField || creatingNew}
              onClick={onDeleteSelected}
            />
          </Stack>
        </Stack>

        {hasPolygon && (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
            <Chip label={`Points: ${fieldBorder?.length ?? 0}`} size="small" />
            {metrics?.areaHa != null && (
              <Chip label={`Area: ${metrics.areaHa.toFixed(2)} ha`} size="small" />
            )}
            {selectedFieldId != null && !creatingNew && (
              <Chip label={`Saved #${selectedFieldId}`} size="small" variant="outlined" />
            )}
          </Box>
        )}
      </Stack>
    </Paper>
  );
}
