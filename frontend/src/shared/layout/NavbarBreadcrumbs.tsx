import { styled } from "@mui/material/styles";
import Typography from "@mui/material/Typography";
import Breadcrumbs, { breadcrumbsClasses } from "@mui/material/Breadcrumbs";
import NavigateNextRoundedIcon from "@mui/icons-material/NavigateNextRounded";
import Link from "@mui/material/Link";
import { Link as RouterLink, useLocation } from "react-router-dom";

const StyledBreadcrumbs = styled(Breadcrumbs)(({ theme }) => ({
  margin: theme.spacing(1, 0),
  [`& .${breadcrumbsClasses.separator}`]: {
    color: (theme.vars || theme).palette.action.disabled,
    margin: 1,
  },
  [`& .${breadcrumbsClasses.ol}`]: {
    alignItems: "center",
  },
}));

function toTitle(segment: string) {
  const overrides: Record<string, string> = {
    insights: "Insights",
    fleet: "Fleet",
    settings: "Settings",
    account: "Account",
    photogrammetry: "Photogrammetry",
    animalfarm: "Animal Farm",
    privatepatrol: "Property Patrol Mission",
    "property-patrol": "Property Patrol Mission",
    field: "Field Operations",
    warehouse: "Warehouse",
    "video-analysis": "Video Analysis",
  };

  if (overrides[segment]) return overrides[segment];

  // "tasks" -> "Tasks", "user-settings" -> "User Settings"
  return segment
    .split("-")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export default function NavbarBreadcrumbs() {
  const { pathname } = useLocation();

  // Examples:
  // /dashboard           -> ["dashboard"]
  // /dashboard/controlled -> ["dashboard", "controlled"]
  const segments = pathname.split("/").filter(Boolean);

  // If you're inside /dashboard/... grab the part after "dashboard"
  const dashboardIndex = segments.indexOf("dashboard");
  const subSegments =
    dashboardIndex >= 0 ? segments.slice(dashboardIndex + 1) : [];

  // If no sub route, it's Home
  const current = subSegments.length === 0 ? "home" : subSegments[subSegments.length - 1];

  const currentLabel = current === "home" ? "Overview" : toTitle(current);

  return (
    <StyledBreadcrumbs
      aria-label="breadcrumb"
      separator={<NavigateNextRoundedIcon fontSize="small" />}
    >
      <Link
        component={RouterLink}
        to="/dashboard"
        underline="hover"
        color="inherit"
        variant="body1"
      >
        Operations Hub
      </Link>

      <Typography variant="body1" sx={{ color: "text.primary", fontWeight: 500 }}>
        {currentLabel}
      </Typography>
    </StyledBreadcrumbs>
  );
}
