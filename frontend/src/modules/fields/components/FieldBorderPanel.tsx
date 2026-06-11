import {
  Chip,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { BorderMetrics, LonLat } from "../types";

export function FieldBorderPanel({
  fieldName,
  selectedFieldId,
  fieldBorder,
  metrics,
  selectedFieldDisplayId,
  savingField,
  onFieldNameChange,
  onSaveOrUpdate,
  onClearBorder,
  onNewField,
  labels,
}: {
  fieldName: string;
  selectedFieldId: number | null;
  fieldBorder: LonLat[] | null;
  metrics?: BorderMetrics | null;
  selectedFieldDisplayId?: number | null;
  savingField: boolean;
  onFieldNameChange: (name: string) => void;
  onSaveOrUpdate: () => void | Promise<void>;
  onClearBorder: () => void;
  onNewField: () => void;
  labels?: {
    panelTitle?: string;
    panelInfo?: string;
    nameLabel?: string;
    saveTitle?: string;
    updateTitle?: string;
    newTitle?: string;
  };
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, flex: 1, minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        <InfoLabel
          label={labels?.panelTitle ?? "Field Border"}
          info={
            labels?.panelInfo ??
            "Draw a polygon on the map. We store coordinates as [lon, lat] (GeoJSON order)."
          }
        />
      </Typography>

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={0.25}
        alignItems="center"
        sx={{ flexWrap: "wrap" }}
      >
        <TextField
          variant="filled"
          size="small"
          label={labels?.nameLabel ?? "Field name"}
          value={fieldName}
          onChange={(e) => onFieldNameChange(e.target.value)}
          sx={{ minWidth: 220 }}
        />

        <ActionIconButton
          variant={selectedFieldId ? "upgrade" : "add"}
          title={
            selectedFieldId
              ? (labels?.updateTitle ?? "Update field border")
              : (labels?.saveTitle ?? "Save field border")
          }
          color="primary"
          loading={savingField}
          disabled={savingField || !fieldBorder || fieldBorder.length < 3}
          onClick={() => void onSaveOrUpdate()}
        />

        <ActionIconButton
          variant="delete"
          title="Clear border"
          onClick={onClearBorder}
        />

        <ActionIconButton variant="add" title={labels?.newTitle ?? "New field"} onClick={onNewField} />

        {fieldBorder && (
          <>
            <Chip label={`Points: ${fieldBorder.length}`} size="small" />
            {metrics?.areaHa != null && (
              <Chip label={`Area: ${metrics.areaHa.toFixed(2)} ha`} size="small" />
            )}
            {metrics?.centroid && (
              <Chip
                label={`Centroid: ${metrics.centroid.lat.toFixed(5)}, ${metrics.centroid.lng.toFixed(5)}`}
                size="small"
              />
            )}
            {selectedFieldDisplayId != null && (
              <Chip label={`Selected: #${selectedFieldDisplayId}`} size="small" />
            )}
          </>
        )}
      </Stack>
    </Paper>
  );
}
