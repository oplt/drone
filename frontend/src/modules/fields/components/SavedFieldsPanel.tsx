import {
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";

type SavedFieldOption = {
  id: number;
  name: string;
};

export function SavedFieldsPanel({
  fields,
  selectedFieldId,
  selectedField,
  loadingFields,
  deletingField,
  onSelectField,
  onRefresh,
  onFocusSelected,
  onDeleteSelected,
  labels,
}: {
  fields: SavedFieldOption[];
  selectedFieldId: number | null;
  selectedField: SavedFieldOption | null;
  loadingFields: boolean;
  deletingField: boolean;
  onSelectField: (fieldId: number | null) => void;
  onRefresh: () => void;
  onFocusSelected: () => void;
  onDeleteSelected: () => void;
  labels?: {
    panelTitle?: string;
    panelInfo?: string;
    selectLabel?: string;
    refreshTitle?: string;
    focusTitle?: string;
    deleteTitle?: string;
  };
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        <InfoLabel
          label={labels?.panelTitle ?? "Saved Fields"}
          info={labels?.panelInfo ?? "Select a saved field to load and focus it on the map."}
        />
      </Typography>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={0.25}
        alignItems={{ xs: "stretch", sm: "flex-start" }}
      >
        <TextField
          variant="filled"
          select
          size="small"
          fullWidth
          label={labels?.selectLabel ?? "Saved fields (database)"}
          value={selectedFieldId == null ? "" : String(selectedFieldId)}
          onChange={(e) => {
            const raw = e.target.value;
            onSelectField(raw ? Number(raw) : null);
          }}
          helperText={
            selectedField
              ? `Selected: ${selectedField.name} (#${selectedField.id})`
              : undefined
          }
          sx={{ flexGrow: 1, minWidth: 0 }}
        >
          <MenuItem value="">None</MenuItem>
          {fields.map((field) => (
            <MenuItem key={field.id} value={String(field.id)}>
              {field.name} (#{field.id})
            </MenuItem>
          ))}
        </TextField>

        <Stack direction="row" spacing={0.25} sx={{ flexShrink: 0 }}>
          <ActionIconButton
            variant="refresh"
            title={labels?.refreshTitle ?? "Refresh saved fields"}
            loading={loadingFields}
            onClick={onRefresh}
          />
          <ActionIconButton
            variant="focus"
            title={labels?.focusTitle ?? "Focus selected field"}
            disabled={!selectedField}
            onClick={onFocusSelected}
          />
          <ActionIconButton
            variant="delete"
            title={labels?.deleteTitle ?? "Delete selected field"}
            color="error"
            loading={deletingField}
            disabled={!selectedField}
            onClick={onDeleteSelected}
          />
        </Stack>
      </Stack>
    </Paper>
  );
}
