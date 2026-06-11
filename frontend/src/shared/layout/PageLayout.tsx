import type { ReactNode } from "react";
import type { SxProps, Theme } from "@mui/material/styles";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

export type PageMetric = {
  label: string;
  value: string;
  caption?: string;
  tooltip?: string;
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
        <Box sx={{ px: { xs: 0, md: 1 }, pt: { xs: 1, md: 2 } }}>
          <Stack spacing={3}>
            <Stack
              direction={{ xs: "column", lg: "row" }}
              spacing={3}
              justifyContent="space-between"
            >
              <Stack spacing={1.5} sx={{ maxWidth: 760 }}>
                {eyebrow ? (
                  <Typography variant="caption" color="text.secondary">
                    {eyebrow}
                  </Typography>
                ) : null}
                <Typography variant="h3" sx={{ color: "text.primary", fontWeight: 500 }}>
                  {title}
                </Typography>
                <Typography variant="body2" color="text.secondary">
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
                        <Grid
                          key={`${metric.label}-${metric.value}`}
                          size={{ xs: 12, sm: 4 }}
                        >
                          <Tooltip
                            title={metric.tooltip ?? ""}
                            arrow
                            disableHoverListener={!metric.tooltip}
                          >
                            <Paper
                              variant="outlined"
                              sx={{
                                p: 2,
                                height: "100%",
                                borderRadius: 3,
                                border: "none",
                                backgroundColor: "grey.50",
                              }}
                            >
                              <Stack spacing={0.5}>
                                <Typography variant="caption" color="text.secondary">
                                  {metric.label}
                                </Typography>
                                <Typography
                                  variant="h4"
                                  sx={{
                                    fontWeight: 500,
                                    lineHeight: 1.18,
                                    color: "text.primary",
                                  }}
                                >
                                  {metric.value}
                                </Typography>
                                {metric.caption ? (
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                  >
                                    {metric.caption}
                                  </Typography>
                                ) : null}
                              </Stack>
                            </Paper>
                          </Tooltip>
                        </Grid>
                      ))}
                    </Grid>
                  </Grid>
                ) : null}
                {hero ? (
                  <Grid size={{ xs: 12, xl: metrics.length > 0 ? 5 : 12 }}>
                    {hero}
                  </Grid>
                ) : null}
              </Grid>
            )}
          </Stack>
        </Box>

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
          borderRadius: 3,
          border: "none",
          backgroundColor: "background.paper",
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
            {title ? (
              <Typography variant="h6" sx={{ color: "text.primary" }}>
                {title}
              </Typography>
            ) : null}
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
