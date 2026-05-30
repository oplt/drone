import BlockRoundedIcon from "@mui/icons-material/BlockRounded";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ActionIconButton } from "./ActionIconButton";

export type PermissionDeniedProps = {
  title?: string;
  message?: string;
  onGoBack?: () => void;
  backLabel?: string;
};

export default function PermissionDenied({
  title = "Access denied",
  message = "You do not have permission to view this page. Contact your administrator if you believe this is an error.",
  onGoBack,
  backLabel = "Go back",
}: PermissionDeniedProps) {
  return (
    <Box
      role="alert"
      aria-live="polite"
      sx={{
        width: "100%",
        maxWidth: 560,
        mx: "auto",
        py: { xs: 5, md: 8 },
        px: { xs: 2, md: 3 },
      }}
    >
      <Stack spacing={2} alignItems="flex-start">
        <BlockRoundedIcon color="error" aria-hidden="true" sx={{ fontSize: 40 }} />
        <Typography variant="h5" component="h2">
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {message}
        </Typography>
        {onGoBack ? (
          <ActionIconButton variant="undo" title={backLabel} onClick={onGoBack} />
        ) : null}
      </Stack>
    </Box>
  );
}
