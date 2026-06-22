import AgricultureIcon from "@mui/icons-material/Agriculture";
import CloseIcon from "@mui/icons-material/Close";
import FenceIcon from "@mui/icons-material/Fence";
import GrassIcon from "@mui/icons-material/Grass";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import {
  Box,
  Button,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";

export type MapShapeActionVariant = "field" | "geofence" | "farm-border";

const VARIANT_COPY: Record<
  MapShapeActionVariant,
  { title: string; subtitle: string; nameLabel: string; saveTitle: string; updateTitle: string }
> = {
  field: {
    title: "Add field",
    subtitle: "Save this drawn boundary as a field for missions and analysis.",
    nameLabel: "Field name",
    saveTitle: "Save field",
    updateTitle: "Update field",
  },
  geofence: {
    title: "Property geofence",
    subtitle: "Save this boundary as the patrol property geofence.",
    nameLabel: "Geofence name",
    saveTitle: "Save geofence",
    updateTitle: "Update geofence",
  },
  "farm-border": {
    title: "Farm border",
    subtitle: "Save this pasture boundary for herd monitoring.",
    nameLabel: "Border name",
    saveTitle: "Save farm border",
    updateTitle: "Update farm border",
  },
};

function VariantIcon({ variant }: { variant: MapShapeActionVariant }) {
  const sx = { fontSize: 22, color: "primary.main" };
  if (variant === "geofence") return <FenceIcon sx={sx} />;
  if (variant === "farm-border") return <GrassIcon sx={sx} />;
  return <AgricultureIcon sx={sx} />;
}

export function MapShapeActionPopover({
  open,
  variant,
  name,
  saving,
  isUpdate,
  placement = "right",
  onNameChange,
  onSave,
  onDismiss,
}: {
  open: boolean;
  variant: MapShapeActionVariant;
  name: string;
  saving?: boolean;
  isUpdate?: boolean;
  placement?: "left" | "right";
  onNameChange: (name: string) => void;
  onSave: () => void | Promise<void>;
  onDismiss: () => void;
}) {
  if (!open) return null;

  const copy = VARIANT_COPY[variant];
  const horizontalAnchor =
    placement === "left"
      ? { left: 12, right: "auto" as const }
      : { right: 12, left: "auto" as const };

  return (
    <Paper
      elevation={4}
      sx={{
        position: "absolute",
        top: "50%",
        transform: "translateY(-50%)",
        zIndex: 1400,
        pointerEvents: "auto",
        width: { xs: "min(320px, calc(100% - 80px))", sm: 320 },
        maxWidth: "calc(100% - 24px)",
        p: 1.5,
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        ...horizontalAnchor,
      }}
    >
      <Stack spacing={1.25}>
        <Stack direction="row" spacing={1} alignItems="flex-start">
          <Box sx={{ pt: 0.25 }}>
            <VariantIcon variant={variant} />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle2" fontWeight={700}>
              {copy.title}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {copy.subtitle}
            </Typography>
          </Box>
          <Tooltip title="Dismiss">
            <IconButton size="small" onClick={onDismiss} aria-label="Dismiss shape action">
              <CloseIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>

        <TextField
          size="small"
          fullWidth
          label={copy.nameLabel}
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
        />

        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button
            size="small"
            variant="contained"
            color="primary"
            startIcon={<SaveOutlinedIcon />}
            disabled={!name.trim() || saving}
            onClick={() => void onSave()}
          >
            {saving ? "Saving…" : isUpdate ? copy.updateTitle : copy.saveTitle}
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
