import type { ReactNode } from "react";
import { alpha } from "@mui/material/styles";
import type { SxProps, Theme } from "@mui/material/styles";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export type PageMetric = {
  label: string;
  value: string;
  caption?: string;
};

type PageLayoutProps = {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
  metrics?: PageMetric[];
  hero?: ReactNode;
  children: ReactNode;
  maxWidth?: number | string;
};

type PageSectionProps = {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  sx?: SxProps<Theme>;
};

export default function PageLayout({
  eyebrow,
  title,
  description,
  actions,
  metrics = [],
  hero,
  children,
  maxWidth = 1700,
}: PageLayoutProps) {
  return (
    <Box sx={{ width: "100%", maxWidth, px: { xs: 0, sm: 1 } }}>
      <Stack spacing={3}>
        <Paper
          variant="outlined"
          sx={(theme) => ({
            p: { xs: 3, md: 4 },
            borderRadius: 5,
            background:
              "linear-gradient(145deg, hsla(35, 85%, 95%, 0.88), hsla(166, 58%, 95%, 0.84))",
            borderColor: alpha(theme.palette.primary.main, 0.16),
            ...theme.applyStyles("dark", {
              background:
                "linear-gradient(145deg, hsla(28, 24%, 13%, 0.92), hsla(168, 28%, 14%, 0.84))",
            }),
          })}
        >
          <Stack spacing={3}>
            <Stack
              direction={{ xs: "column", lg: "row" }}
              spacing={3}
              justifyContent="space-between"
            >
              <Stack spacing={1.25} sx={{ maxWidth: 760 }}>
                {eyebrow ? (
                  <Typography variant="overline" sx={{ letterSpacing: 2, color: "text.secondary" }}>
                    {eyebrow}
                  </Typography>
                ) : null}
                <Typography variant="h3">{title}</Typography>
                <Typography variant="body1" color="text.secondary">
                  {description}
                </Typography>
              </Stack>
              {actions ? (
                <Box sx={{ width: { xs: "100%", lg: "auto" } }}>{actions}</Box>
              ) : null}
            </Stack>

            {(metrics.length > 0 || hero) && (
              <Grid container spacing={2}>
                {metrics.length > 0 ? (
                  <Grid size={{ xs: 12, xl: hero ? 7 : 12 }}>
                    <Grid container spacing={2}>
                      {metrics.map((metric) => (
                        <Grid key={`${metric.label}-${metric.value}`} size={{ xs: 12, sm: 4 }}>
                          <Paper
                            variant="outlined"
                            sx={(theme) => ({
                              p: 2.25,
                              height: "100%",
                              borderRadius: 4,
                              backgroundColor: "rgba(255,255,255,0.66)",
                              backdropFilter: "blur(12px)",
                              ...theme.applyStyles("dark", {
                                backgroundColor: "rgba(17,22,26,0.72)",
                              }),
                            })}
                          >
                            <Stack spacing={0.75}>
                              <Typography variant="caption" color="text.secondary">
                                {metric.label}
                              </Typography>
                              <Typography variant="h5">{metric.value}</Typography>
                              {metric.caption ? (
                                <Typography variant="body2" color="text.secondary">
                                  {metric.caption}
                                </Typography>
                              ) : null}
                            </Stack>
                          </Paper>
                        </Grid>
                      ))}
                    </Grid>
                  </Grid>
                ) : null}
                {hero ? <Grid size={{ xs: 12, xl: metrics.length > 0 ? 5 : 12 }}>{hero}</Grid> : null}
              </Grid>
            )}
          </Stack>
        </Paper>

        {children}
      </Stack>
    </Box>
  );
}

export function PageSection({
  title,
  description,
  action,
  children,
  sx,
}: PageSectionProps) {
  return (
    <Paper
      variant="outlined"
      sx={[
        {
          p: { xs: 2.5, md: 3 },
          borderRadius: 4,
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      {(title || description || action) && (
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={2}
          justifyContent="space-between"
          alignItems={{ xs: "flex-start", md: "center" }}
          sx={{ mb: 2.5 }}
        >
          <Stack spacing={0.5}>
            {title ? <Typography variant="h6">{title}</Typography> : null}
            {description ? (
              <Typography variant="body2" color="text.secondary">
                {description}
              </Typography>
            ) : null}
          </Stack>
          {action ? <Box>{action}</Box> : null}
        </Stack>
      )}
      {children}
    </Paper>
  );
}
