import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import CssBaseline from "@mui/material/CssBaseline";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ChipProps } from "@mui/material/Chip";
import AppTheme from "../shared-theme/AppTheme";
import ColorModeSelect from "../shared-theme/ColorModeSelect";
import { SitemarkIcon } from "../CustomIcons";

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
        sx={(theme) => ({
          minHeight: "100dvh",
          px: { xs: 2, md: 4 },
          py: { xs: 3, md: 4 },
          position: "relative",
          overflow: "hidden",
          "&::before": {
            content: '""',
            position: "absolute",
            inset: 0,
            zIndex: 0,
            backgroundImage:
              "radial-gradient(circle at 8% 10%, hsla(174, 60%, 88%, 0.55), transparent 34%), radial-gradient(circle at 88% 12%, hsla(35, 95%, 86%, 0.42), transparent 30%), linear-gradient(180deg, rgba(255,255,255,0.5), rgba(255,255,255,0))",
            ...theme.applyStyles("dark", {
              "&::before": {
                backgroundImage:
                  "radial-gradient(circle at 8% 10%, hsla(174, 60%, 24%, 0.42), transparent 34%), radial-gradient(circle at 88% 12%, hsla(35, 95%, 24%, 0.28), transparent 30%), linear-gradient(180deg, rgba(9,13,16,0.38), rgba(9,13,16,0))",
              },
            }),
          },
        })}
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
            gap: { xs: 3, md: 5 },
            alignItems: "stretch",
          }}
        >
          <Card
            variant="outlined"
            sx={(theme) => ({
              minHeight: { md: 720 },
              px: { xs: 3, md: 5 },
              py: { xs: 3.5, md: 5 },
              justifyContent: "space-between",
              background:
                "linear-gradient(160deg, rgba(252,253,252,0.92), rgba(239,247,244,0.88))",
              ...theme.applyStyles("dark", {
                background:
                  "linear-gradient(160deg, rgba(15,20,24,0.92), rgba(17,29,27,0.88))",
              }),
            })}
          >
            <Stack spacing={3.5}>
              <Stack spacing={2}>
                <SitemarkIcon />
                <Chip label={badge} color={badgeColor} sx={{ width: "fit-content" }} />
              </Stack>
              <Stack spacing={2}>
                <Typography
                  variant="h1"
                  sx={{
                    maxWidth: 560,
                    fontSize: { xs: "2.5rem", md: "4rem" },
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
            sx={(theme) => ({
              justifyContent: "center",
              px: { xs: 3, md: 4 },
              py: { xs: 3.5, md: 4.5 },
              background: "rgba(255,255,255,0.86)",
              backdropFilter: "blur(20px)",
              ...theme.applyStyles("dark", {
                background: "rgba(14,18,22,0.82)",
              }),
            })}
          >
            <Stack spacing={3}>
              <Stack spacing={1}>
                <Typography component="h1" variant="h3">
                  {formTitle}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {formSubtitle}
                </Typography>
              </Stack>
              <Divider />
              {children}
              {footer ? <Box>{footer}</Box> : null}
            </Stack>
          </Card>
        </Box>
      </Box>
    </AppTheme>
  );
}
