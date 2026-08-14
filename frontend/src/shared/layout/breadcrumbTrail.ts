/** Explicit IA labels for registered route segments. */
export const BREADCRUMB_LABELS: Record<string, string> = {
  insights: "History",
  fleet: "Fleet",
  settings: "Settings",
  account: "Account",
  photogrammetry: "Photogrammetry",
  animalfarm: "Animal Farm",
  privatepatrol: "Property Inspection",
  "property-patrol": "Property Inspection",
  field: "Missions",
  agriculture: "Agriculture",
  fields: "Fields",
  flights: "Flights",
  analysis: "Analysis",
  "vision-models": "Datasets & Training",
  "training-runs": "Training run",
  datasets: "Datasets",
  label: "Labeling",
  warehouse: "Warehouse",
  "video-analysis": "Video Analysis",
  observability: "Observability",
  controlled: "Live Operations",
  templates: "Automations",
  admin: "Admin",
  missions: "Missions",
  timeline: "Timeline",
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const LONG_ID_RE = /^[0-9a-f]{16,}$/i;

export function truncateIdLabel(segment: string, max = 8): string {
  if (UUID_RE.test(segment) || LONG_ID_RE.test(segment) || segment.length > 20) {
    return `${segment.slice(0, max)}…`;
  }
  return segment;
}

export function toBreadcrumbLabel(segment: string): string {
  if (BREADCRUMB_LABELS[segment]) return BREADCRUMB_LABELS[segment];
  if (UUID_RE.test(segment) || LONG_ID_RE.test(segment) || /^\d+$/.test(segment)) {
    return truncateIdLabel(segment);
  }
  return segment
    .split("-")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export type BreadcrumbCrumb = {
  label: string;
  to: string;
  current: boolean;
};

/** Build crumb trail for dashboard (and legacy /observability) paths. */
export function buildBreadcrumbTrail(pathname: string): BreadcrumbCrumb[] {
  const segments = pathname.split("/").filter(Boolean);

  if (segments[0] === "observability") {
    return [
      { label: "Overview", to: "/dashboard", current: false },
      { label: "Observability", to: "/dashboard/observability", current: true },
    ];
  }

  const dashboardIndex = segments.indexOf("dashboard");
  if (dashboardIndex < 0) {
    return [{ label: "Overview", to: "/dashboard", current: true }];
  }

  const subSegments = segments.slice(dashboardIndex + 1);
  const crumbs: BreadcrumbCrumb[] = [
    {
      label: "Overview",
      to: "/dashboard",
      current: subSegments.length === 0,
    },
  ];

  let path = "/dashboard";
  subSegments.forEach((segment, index) => {
    path += `/${segment}`;
    crumbs.push({
      label: toBreadcrumbLabel(segment),
      to: path,
      current: index === subSegments.length - 1,
    });
  });

  return crumbs;
}
