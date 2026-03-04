import {
  Chip,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import InfoLabel from "../InfoLabel";

type LonLat = [number, number];

type BorderMetrics = {
  areaHa?: number | null;
  centroid?: {
    lat: number;
    lng: number;
  } | null;
};

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
}: {
  fieldName: string;
  selectedFieldId: number | null;
  fieldBorder: LonLat[] | null;
  metrics?: BorderMetrics | null;
  selectedFieldDisplayId?: number | null;
  savingField: boolean;
  onFieldNameChange: (name: string) => void;
  onSaveOrUpdate: () => void;
  onClearBorder: () => void;
  onNewField: () => void;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, flex: 1, minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        <InfoLabel
          label="Field Border"
          info="Draw a polygon on the map. We store coordinates as [lon, lat] (GeoJSON order)."
        />
      </Typography>

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        alignItems="center"
        sx={{ flexWrap: "wrap" }}
      >
        <TextField
          variant="filled"
          size="small"
          label="Field name"
          value={fieldName}
          onChange={(e) => onFieldNameChange(e.target.value)}
          sx={{ minWidth: 220 }}
        />

        <Tooltip title={selectedFieldId ? "Update field border" : "Save field border"}>
          <span>
            <IconButton
              size="small"
              color="primary"
              onClick={onSaveOrUpdate}
              disabled={savingField || !fieldBorder || fieldBorder.length < 3}
              aria-label={selectedFieldId ? "Update field border" : "Save field border"}
              sx={{
                border: "1px solid",
                borderColor: "primary.main",
                borderRadius: 1,
                bgcolor: "primary.main",
                color: "primary.contrastText",
                "&:hover": {
                  bgcolor: "primary.dark",
                },
              }}
            >
              {savingField ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <SaveOutlinedIcon fontSize="small" />
              )}
            </IconButton>
          </span>
        </Tooltip>

        <Tooltip title="Clear border">
          <span>
            <IconButton
              size="small"
              onClick={onClearBorder}
              aria-label="Clear border"
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              <DeleteOutlineOutlinedIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>

        <Tooltip title="New field">
          <span>
            <IconButton
              size="small"
              onClick={onNewField}
              aria-label="New field"
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              <AddCircleOutlineIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>

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
