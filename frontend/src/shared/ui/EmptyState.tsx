import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

export type EmptyStateProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
};

export default function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 3, md: 4 },
        borderRadius: 3,
        textAlign: "center",
        width: "100%",
      }}
    >
      <Stack spacing={2} alignItems="center">
        {icon ? <Box aria-hidden="true">{icon}</Box> : null}
        <Typography variant="h6" component="h2">
          {title}
        </Typography>
        {description ? (
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480 }}>
            {description}
          </Typography>
        ) : null}
        {action}
      </Stack>
    </Paper>
  );
}
