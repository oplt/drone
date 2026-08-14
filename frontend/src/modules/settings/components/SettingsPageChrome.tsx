import { Box } from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";

type SettingsPageActionsProps = {
  loading: boolean;
  saving: boolean;
  dirty: boolean;
  onReset: () => void;
  onSave: () => void;
};

export function SettingsPageActions({
  loading,
  saving,
  dirty,
  onReset,
  onSave,
}: SettingsPageActionsProps) {
  return (
    <Box sx={{ mt: 4, display: "flex", justifyContent: "flex-end", gap: 0.5 }}>
      <ActionIconButton
        variant="undo"
        title="Reset"
        disabled={loading || saving}
        onClick={onReset}
      />
      <ActionIconButton
        variant="upgrade"
        title={saving ? "Saving…" : "Save All Changes"}
        color="primary"
        loading={saving}
        disabled={!dirty || saving || loading}
        onClick={onSave}
      />
    </Box>
  );
}
