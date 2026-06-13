import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import LaunchRoundedIcon from "@mui/icons-material/LaunchRounded";

type ObservabilityShortcutCardProps = {
  title: string;
  description: string;
  buttonLabel: string;
  url: string | null | undefined;
  icon: ReactNode;
  onOpen: (url: string) => void;
  restricted?: boolean;
};

export default function ObservabilityShortcutCard({
  title,
  description,
  buttonLabel,
  url,
  icon,
  onOpen,
  restricted,
}: ObservabilityShortcutCardProps) {
  const configured = Boolean(url);
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2.5,
        height: "100%",
        borderRadius: 2,
        borderColor: "divider",
      }}
    >
      <Stack spacing={2} sx={{ height: "100%" }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Box
            sx={{
              display: "grid",
              placeItems: "center",
              width: 38,
              height: 38,
              borderRadius: 1.5,
              backgroundColor: "action.hover",
              color: "primary.main",
            }}
          >
            {icon}
          </Box>
          <Stack spacing={0.25}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {title}
            </Typography>
            {restricted ? <Chip size="small" label="Admin / developer" /> : null}
          </Stack>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
          {description}
        </Typography>
        <Button
          variant={configured ? "contained" : "outlined"}
          endIcon={<LaunchRoundedIcon />}
          disabled={!configured}
          onClick={() => {
            if (url) onOpen(url);
          }}
          sx={{ alignSelf: "flex-start" }}
        >
          {configured ? buttonLabel : "Not configured"}
        </Button>
      </Stack>
    </Paper>
  );
}
