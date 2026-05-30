import type { ReactNode } from "react";
import { Box, Divider, Stack, Typography } from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";

type WarehouseDrawerSectionProps = {
  title: string;
  info: string;
  children: ReactNode;
  action?: ReactNode;
  showDivider?: boolean;
};

export function WarehouseDrawerSection({
  title,
  info,
  children,
  action,
  showDivider = true,
}: WarehouseDrawerSectionProps) {
  return (
    <Box component="section">
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 1 }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          <InfoLabel label={title} info={info} />
        </Typography>
        {action}
      </Stack>
      {children}
      {showDivider && <Divider sx={{ mt: 2 }} />}
    </Box>
  );
}
