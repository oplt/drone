import Box from "@mui/material/Box";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { healthStatusTextColor } from "../healthStatusPresentation";
import type { HealthState } from "../types";

export function titleCaseStatus(status: HealthState) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

type HealthStatusCardProps = {
  title: string;
  value: string;
  status: HealthState;
  caption?: string;
  href?: string | null;
  loading?: boolean;
};

export default function HealthStatusCard({
  title,
  value,
  status,
  caption,
  href,
  loading,
}: HealthStatusCardProps) {
  const valueColor = healthStatusTextColor(status);

  return (
    <Box
      component={href ? "a" : "div"}
      href={href ?? undefined}
      target={href ? "_blank" : undefined}
      rel={href ? "noopener noreferrer" : undefined}
      sx={{
        p: 1.25,
        height: "100%",
        minHeight: 72,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        backgroundColor: "background.paper",
        borderRight: "1px solid",
        borderColor: "divider",
        textDecoration: "none",
        color: "inherit",
        cursor: href ? "pointer" : "default",
        transition: (theme) =>
          theme.transitions.create(["background-color"], { duration: theme.transitions.duration.shorter }),
        ...(href
          ? {
              "&:hover": {
                backgroundColor: "action.hover",
              },
            }
          : {}),
      }}
    >
      <Stack spacing={0.75}>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontWeight: 600, letterSpacing: 0.2, lineHeight: 1.2 }}
          noWrap
        >
          {title}
        </Typography>
        {loading ? (
          <Skeleton variant="text" width="70%" height={24} />
        ) : (
          <Typography
            variant="body1"
            noWrap
            sx={{
              fontWeight: 600,
              lineHeight: 1.2,
              color: valueColor,
            }}
          >
            {value}
          </Typography>
        )}
        {caption ? (
          <Typography
            variant="caption"
            color="text.secondary"
            noWrap
            sx={{ display: { xs: "none", lg: "block" } }}
          >
            {caption}
          </Typography>
        ) : null}
      </Stack>
    </Box>
  );
}
