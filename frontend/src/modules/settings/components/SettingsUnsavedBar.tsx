import { Button, Paper, Stack } from "@mui/material";
import { SaveIndicator } from "../../../shared/ui/SaveIndicator";

type SettingsUnsavedBarProps = {
  dirty: boolean;
  saving: boolean;
  loading: boolean;
  onDiscard: () => void;
  onSave: () => void;
};

export function SettingsUnsavedBar({
  dirty,
  saving,
  loading,
  onDiscard,
  onSave,
}: SettingsUnsavedBarProps) {
  if (!dirty && !saving) return null;

  return (
    <Paper
      elevation={8}
      role="status"
      aria-live="polite"
      sx={{
        position: "sticky",
        bottom: 0,
        zIndex: (theme) => theme.zIndex.appBar,
        mx: { xs: 0, md: 3 },
        mb: 1,
        px: 2,
        py: 1.25,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 2,
        flexWrap: "wrap",
        borderTop: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
        <SaveIndicator
          state={saving ? "saving" : dirty ? "dirty" : "saved"}
          labels={{ saved: "All changes saved", dirty: "Unsaved settings changes" }}
        />
        <Button size="small" onClick={onDiscard} disabled={saving || !dirty}>
          Discard
        </Button>
        <Button
          size="small"
          variant="contained"
          onClick={onSave}
          disabled={saving || loading || !dirty}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
      </Stack>
    </Paper>
  );
}
