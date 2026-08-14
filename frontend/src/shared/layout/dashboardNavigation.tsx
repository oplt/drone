import type { ReactNode } from "react";
import AssignmentRoundedIcon from "@mui/icons-material/AssignmentRounded";
import AgricultureIcon from "@mui/icons-material/Agriculture";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import EmojiNatureRoundedIcon from "@mui/icons-material/EmojiNatureRounded";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import HomeRoundedIcon from "@mui/icons-material/HomeRounded";
import MapRoundedIcon from "@mui/icons-material/MapRounded";
import PhotoCameraRoundedIcon from "@mui/icons-material/PhotoCameraRounded";
import PrecisionManufacturingRoundedIcon from "@mui/icons-material/PrecisionManufacturingRounded";
import QueryStatsRoundedIcon from "@mui/icons-material/QueryStatsRounded";
import SecurityRoundedIcon from "@mui/icons-material/SecurityRounded";
import SportsEsportsRoundedIcon from "@mui/icons-material/SportsEsportsRounded";
import VideocamRoundedIcon from "@mui/icons-material/VideocamRounded";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import WarehouseRoundedIcon from "@mui/icons-material/WarehouseRounded";
import AdminPanelSettingsRoundedIcon from "@mui/icons-material/AdminPanelSettingsRounded";
import {
  capabilitiesForRole,
  type DashboardNavCapability,
} from "./dashboardNavCapabilities";

export type { DashboardNavCapability };

export type DashboardNavChild = {
  text: string;
  icon: ReactNode;
  path: string;
  capability: DashboardNavCapability;
};

export type DashboardNavEntry = {
  text: string;
  icon: ReactNode;
  path?: string;
  exact?: boolean;
  expandOnly?: boolean;
  capability?: DashboardNavCapability;
  children?: DashboardNavChild[];
};

export type DashboardNavSection = {
  label: string;
  entries: DashboardNavEntry[];
};

/** Product-oriented shell navigation. Paths are stable dashboard routes (aliases live in AppRouter). */
export const dashboardNavigationSections: DashboardNavSection[] = [
  {
    label: "Workspace",
    entries: [
      {
        text: "Overview",
        icon: <HomeRoundedIcon />,
        path: "/dashboard",
        exact: true,
        capability: "workspace.overview",
      },
    ],
  },
  {
    label: "Operations",
    entries: [
      {
        text: "Missions",
        icon: <MapRoundedIcon />,
        path: "/dashboard/field",
        capability: "operations.missions",
      },
      {
        text: "Fleet",
        icon: <PrecisionManufacturingRoundedIcon />,
        path: "/dashboard/fleet",
        capability: "operations.fleet",
      },
      {
        text: "Live Operations",
        icon: <SportsEsportsRoundedIcon />,
        path: "/dashboard/controlled",
        capability: "operations.live",
      },
      {
        text: "History",
        icon: <HistoryRoundedIcon />,
        path: "/dashboard/insights",
        capability: "operations.history",
      },
    ],
  },
  {
    label: "Applications",
    entries: [
      {
        text: "Applications",
        icon: <AssignmentRoundedIcon />,
        expandOnly: true,
        children: [
          {
            text: "Agriculture",
            icon: <AgricultureIcon />,
            path: "/dashboard/agriculture/fields",
            capability: "applications.agriculture",
          },
          {
            text: "Property Inspection",
            icon: <SecurityRoundedIcon />,
            path: "/dashboard/property-patrol",
            capability: "applications.property",
          },
          {
            text: "Warehouse",
            icon: <WarehouseRoundedIcon />,
            path: "/dashboard/warehouse",
            capability: "applications.warehouse",
          },
          {
            text: "Photogrammetry",
            icon: <PhotoCameraRoundedIcon />,
            path: "/dashboard/photogrammetry",
            capability: "applications.photogrammetry",
          },
          {
            text: "Animal Farm",
            icon: <EmojiNatureRoundedIcon />,
            path: "/dashboard/animalfarm",
            capability: "applications.animalfarm",
          },
        ],
      },
    ],
  },
  {
    label: "AI & Models",
    entries: [
      {
        text: "Datasets & Training",
        icon: <VisibilityRoundedIcon />,
        path: "/dashboard/agriculture/vision-models",
        capability: "ai.datasets",
      },
      {
        text: "Video Analysis",
        icon: <VideocamRoundedIcon />,
        path: "/dashboard/video-analysis",
        capability: "ai.video_analysis",
      },
      {
        text: "Automations",
        icon: <ContentCopyRoundedIcon />,
        path: "/dashboard/templates",
        capability: "ai.automations",
      },
    ],
  },
  {
    label: "Administration",
    entries: [
      {
        text: "System",
        icon: <QueryStatsRoundedIcon />,
        path: "/dashboard/observability",
        capability: "admin.system",
      },
      {
        text: "Admin",
        icon: <AdminPanelSettingsRoundedIcon />,
        path: "/dashboard/admin",
        capability: "admin.panel",
      },
    ],
  },
];

function filterEntry(
  entry: DashboardNavEntry,
  capabilities: Set<DashboardNavCapability>,
): DashboardNavEntry | null {
  if (entry.children?.length) {
    const children = entry.children.filter((child) =>
      capabilities.has(child.capability),
    );
    if (!children.length) return null;
    return { ...entry, children };
  }
  if (entry.capability && !capabilities.has(entry.capability)) return null;
  return entry;
}

/** Role-aware navigation filter. Hiding items is UX-only; routes stay backend-enforced. */
export function filterDashboardNavigation(
  role?: string | null,
): DashboardNavSection[] {
  const capabilities = capabilitiesForRole(role);
  return dashboardNavigationSections
    .map((section) => ({
      ...section,
      entries: section.entries
        .map((entry) => filterEntry(entry, capabilities))
        .filter((entry): entry is DashboardNavEntry => entry !== null),
    }))
    .filter((section) => section.entries.length > 0);
}

export function allDashboardNavChildren(
  sections: DashboardNavSection[] = dashboardNavigationSections,
): DashboardNavChild[] {
  return sections.flatMap((section) =>
    section.entries.flatMap((entry) => entry.children ?? []),
  );
}

export function isApplicationsRoute(
  pathname: string,
  sections: DashboardNavSection[] = dashboardNavigationSections,
): boolean {
  const applicationPaths = allDashboardNavChildren(sections).map((child) => child.path);
  return applicationPaths.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}
