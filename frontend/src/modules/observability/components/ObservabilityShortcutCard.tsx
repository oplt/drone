import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
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
    <Box
      sx={{
        p: 1.5,
        height: "100%",
        minHeight: 148,
        display: "flex",
        flexDirection: "column",
        backgroundColor: "background.paper",
        borderRight: "1px solid",
        borderBottom: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack spacing={1.25} sx={{ height: "100%" }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Box
            sx={{
              display: "grid",
              placeItems: "center",
              width: 32,
              height: 32,
              flexShrink: 0,
              borderRadius: 1,
              backgroundColor: "action.hover",
              color: "primary.main",
              "& svg": { fontSize: 18 },
            }}
          >
            {icon}
          </Box>
          <Stack spacing={0.25} minWidth={0}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }} noWrap>
              {title}
            </Typography>
            {restricted ? <Chip size="small" label="Admin" sx={{ alignSelf: "flex-start" }} /> : null}
          </Stack>
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            flexGrow: 1,
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            lineHeight: 1.45,
          }}
        >
          {description}
        </Typography>
        <Button
          size="small"
          variant={configured ? "contained" : "outlined"}
          endIcon={<LaunchRoundedIcon fontSize="small" />}
          disabled={!configured}
          onClick={() => {
            if (url) onOpen(url);
          }}
          sx={{ alignSelf: "flex-start" }}
        >
          {configured ? buttonLabel : "Not configured"}
        </Button>
      </Stack>
    </Box>
  );
}
