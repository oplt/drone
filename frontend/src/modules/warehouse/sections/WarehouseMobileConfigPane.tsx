import { Box, Stack, Typography } from "@mui/material";

type WarehouseMobileConfigPaneProps = {
  onOpenSetup: () => void;
  onOpenChecks: () => void;
  onOpenMission: () => void;
};

export function WarehouseMobileConfigPane({
  onOpenSetup,
  onOpenChecks,
  onOpenMission,
}: WarehouseMobileConfigPaneProps) {
  const buttonSx = {
    px: 1.5,
    py: 1,
    minHeight: 44,
    borderRadius: 1,
    border: "1px solid",
    borderColor: "divider",
    bgcolor: "background.paper",
    cursor: "pointer",
  } as const;

  return (
    <Stack spacing={1.5} sx={{ pb: "env(safe-area-inset-bottom, 0px)" }}>
      <Typography variant="body2" color="text.secondary">
        Open setup, checks, or mission controls. On phone these open as bottom
        sheets so the scene stays usable.
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Box component="button" type="button" onClick={onOpenSetup} sx={buttonSx}>
          Setup
        </Box>
        <Box component="button" type="button" onClick={onOpenChecks} sx={buttonSx}>
          Checks
        </Box>
        <Box component="button" type="button" onClick={onOpenMission} sx={buttonSx}>
          Mission
        </Box>
      </Stack>
    </Stack>
  );
}
