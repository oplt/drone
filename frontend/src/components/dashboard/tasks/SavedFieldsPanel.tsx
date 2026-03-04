import {
  CircularProgress,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import CenterFocusStrongIcon from "@mui/icons-material/CenterFocusStrong";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import InfoLabel from "../InfoLabel";

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
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        <InfoLabel
          label="Saved Fields"
          info="Select a saved field to load and focus it on the map."
        />
      </Typography>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        alignItems={{ xs: "stretch", sm: "flex-start" }}
      >
        <TextField
          variant="filled"
          select
          size="small"
          fullWidth
          label="Saved fields (database)"
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

        <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
          <Tooltip title="Refresh saved fields">
            <span>
              <IconButton
                size="small"
                onClick={onRefresh}
                disabled={loadingFields}
                aria-label="Refresh saved fields"
                sx={{
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                }}
              >
                <RefreshIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>

          <Tooltip title="Focus selected field">
            <span>
              <IconButton
                size="small"
                disabled={!selectedField}
                onClick={onFocusSelected}
                aria-label="Focus selected field"
                sx={{
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                }}
              >
                <CenterFocusStrongIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>

          <Tooltip title="Delete selected field">
            <span>
              <IconButton
                size="small"
                color="error"
                disabled={!selectedField || deletingField}
                onClick={onDeleteSelected}
                aria-label="Delete selected field"
                sx={{
                  border: "1px solid",
                  borderColor: "error.main",
                  borderRadius: 1,
                }}
              >
                {deletingField ? (
                  <CircularProgress size={14} color="inherit" />
                ) : (
                  <DeleteOutlineOutlinedIcon fontSize="small" />
                )}
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>
    </Paper>
  );
}
