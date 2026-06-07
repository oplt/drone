import type { ReactNode } from "react";
import { Box, Button, Paper, Stack, Typography } from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";
import SensorsRoundedIcon from "@mui/icons-material/SensorsRounded";
import {
  WarehouseStatusBadge,
  type WarehouseUiStatus,
} from "./WarehouseStatusBadge";

export function WarehouseDashboardCard({
  title,
  subtitle,
  right,
  children,
  sx,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  sx?: SxProps<Theme>;
}) {
  return (
    <Paper
      variant="outlined"
      sx={[
        {
          p: 2,
          borderRadius: 3,
          borderColor: "divider",
          bgcolor: "background.paper",
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <Stack spacing={1.5}>
        <Stack
          direction="row"
          alignItems="flex-start"
          justifyContent="space-between"
          spacing={1.5}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography
              variant="subtitle1"
              sx={{ fontWeight: 700, fontSize: "1rem" }}
            >
              {title}
            </Typography>
            {subtitle ? (
              <Typography variant="body2" color="text.secondary">
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          {right ? <Box sx={{ flexShrink: 0 }}>{right}</Box> : null}
        </Stack>
        {children}
      </Stack>
    </Paper>
  );
}

export function WarehouseEmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <Stack
      alignItems="center"
      justifyContent="center"
      spacing={1.25}
      sx={{ p: 3, textAlign: "center" }}
    >
      <SensorsRoundedIcon sx={{ color: "text.secondary", opacity: 0.7 }} />
      <Box>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {description}
        </Typography>
      </Box>
      {actionLabel && onAction ? (
        <Button size="small" variant="outlined" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </Stack>
  );
}

export type WarehouseStatusStripItem = {
  label: string;
  value: string;
  status: WarehouseUiStatus;
};

export function WarehouseSystemStatusStrip({
  items,
}: {
  items: WarehouseStatusStripItem[];
}) {
  return (
    <Box
      aria-label="System status"
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "repeat(2, minmax(0, 1fr))",
          md: "repeat(5, minmax(0, 1fr))",
        },
        gap: 1,
      }}
    >
      {items.map((item) => (
        <Box
          key={item.label}
          sx={{
            px: 1.25,
            py: 1,
            borderRadius: 2,
            bgcolor: "action.hover",
            minWidth: 0,
          }}
        >
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", fontSize: "0.7rem" }}
          >
            {item.label}
          </Typography>
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            spacing={1}
          >
            <Typography variant="body2" sx={{ fontWeight: 700, minWidth: 0 }}>
              {item.value}
            </Typography>
            <WarehouseStatusBadge status={item.status} />
          </Stack>
        </Box>
      ))}
    </Box>
  );
}
