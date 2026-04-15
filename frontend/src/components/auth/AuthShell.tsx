import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CssBaseline from "@mui/material/CssBaseline";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ChipProps } from "@mui/material/Chip";
import Chip from "@mui/material/Chip";
import AppTheme from "../shared-theme/AppTheme";
import ColorModeSelect from "../shared-theme/ColorModeSelect";

type AuthShellProps = {
  disableCustomTheme?: boolean;
  badge: string;
  badgeColor?: ChipProps["color"];
  title: string;
  description: string;
  formTitle: string;
  formSubtitle: string;
  aside: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
};

export default function AuthShell({
  disableCustomTheme,
  badge,
  badgeColor = "primary",
  title,
  description,
  formTitle,
  formSubtitle,
  aside,
  children,
  footer,
}: AuthShellProps) {
  return (
    <AppTheme disableCustomTheme={disableCustomTheme}>
      <CssBaseline enableColorScheme />
      <Box
        sx={{
          minHeight: "100dvh",
          px: { xs: 2, md: 4 },
          py: { xs: 3, md: 4 },
          position: "relative",
          overflow: "hidden",
          backgroundColor: "background.default",
        }}
      >
        <ColorModeSelect sx={{ position: "fixed", top: 16, right: 16, zIndex: 2 }} />
        <Box
          sx={{
            position: "relative",
            zIndex: 1,
            width: "100%",
            maxWidth: 1180,
            mx: "auto",
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1.08fr) minmax(420px, 0.92fr)" },
            gap: { xs: 3, md: 3 },
            alignItems: "stretch",
          }}
        >
          <Card
            variant="outlined"
            sx={{
              minHeight: { md: 720 },
              px: { xs: 3, md: 5 },
              py: { xs: 3.5, md: 5 },
              justifyContent: "space-between",
              borderRadius: 4,
              border: '1px solid',
              borderColor: 'divider',
              backgroundColor: 'background.paper',
            }}
          >
            <Stack spacing={4}>
              <Stack spacing={2}>
                <Typography
                  variant="caption"
                  sx={{
                    color: "text.secondary",
                  }}
                >
                  DRONE OPS
                </Typography>
                <Chip
                  label={badge}
                  color={badgeColor}
                  sx={{ width: "fit-content" }}
                />
              </Stack>
              <Stack spacing={2}>
                <Typography
                  variant="h1"
                  sx={{
                    maxWidth: 560,
                    fontSize: { xs: "2.25rem", md: "3rem" },
                    color: "text.primary",
                  }}
                >
                  {title}
                </Typography>
                <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 560 }}>
                  {description}
                </Typography>
              </Stack>
            </Stack>
            <Box sx={{ pt: { xs: 3, md: 5 } }}>{aside}</Box>
          </Card>

          <Card
            variant="outlined"
            sx={{
              justifyContent: "center",
              px: { xs: 3, md: 4 },
              py: { xs: 3.5, md: 4.5 },
              borderRadius: 4,
              border: '1px solid',
              borderColor: 'divider',
              backgroundColor: 'background.paper',
            }}
          >
            <Stack spacing={3}>
              <Stack spacing={1}>
                <Typography component="h1" variant="h4">
                  {formTitle}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {formSubtitle}
                </Typography>
              </Stack>
              <Divider sx={{ borderColor: 'divider' }} />
              {children}
              {footer ? <Box>{footer}</Box> : null}
            </Stack>
          </Card>
        </Box>
      </Box>
    </AppTheme>
  );
}
