import { Box, Stack, Typography } from "@mui/material";
import VideocamOffRoundedIcon from "@mui/icons-material/VideocamOffRounded";

export function MissionVideoEmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <Stack
      alignItems="center"
      spacing={1}
      sx={{ color: "common.white", px: 2, textAlign: "center" }}
    >
      <VideocamOffRoundedIcon sx={{ opacity: 0.72 }} />
      <Box>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Typography variant="caption" sx={{ color: "grey.400" }}>
          {description}
        </Typography>
      </Box>
    </Stack>
  );
}
