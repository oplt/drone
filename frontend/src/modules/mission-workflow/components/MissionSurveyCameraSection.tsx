import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import {
  Box,
  Paper,
  Tab,
  Tabs,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";

type SurveyTab = "map" | "setup" | "video-analysis";
export type SurveyLayoutMode = "map-primary" | "video-primary" | "split";

type MissionSurveyCameraSectionProps = {
  video: ReactNode;
  map: ReactNode;
  setup: ReactNode;
  setupSubtitle?: string;
  videoAnalysis?: ReactNode;
  videoAnalysisSubtitle?: string;
  /** Persist layout preference per mission type (e.g. field-survey). */
  layoutStorageKey?: string;
  /** Grow map frame when map-primary (default 520). */
  mapPrimaryHeight?: number;
};

const LAYOUT_LABELS: Record<SurveyLayoutMode, string> = {
  "map-primary": "Map",
  "video-primary": "Video",
  split: "Split",
};

function readStoredLayout(key: string | undefined): SurveyLayoutMode {
  if (!key || typeof window === "undefined") return "map-primary";
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === "map-primary" || raw === "video-primary" || raw === "split") {
      return raw;
    }
  } catch {
    // ignore storage failures
  }
  return "map-primary";
}

export function MissionSurveyCameraSection({
  video,
  map,
  setup,
  setupSubtitle,
  videoAnalysis,
  videoAnalysisSubtitle = "Upload recorded flights and run offline YOLO detection.",
  layoutStorageKey,
  mapPrimaryHeight = 520,
}: MissionSurveyCameraSectionProps) {
  const [tab, setTab] = useState<SurveyTab>("map");
  const [layout, setLayout] = useState<SurveyLayoutMode>(() =>
    readStoredLayout(layoutStorageKey),
  );
  const hasVideoAnalysis = videoAnalysis != null;

  useEffect(() => {
    if (!layoutStorageKey) return;
    try {
      window.localStorage.setItem(layoutStorageKey, layout);
    } catch {
      // ignore
    }
  }, [layout, layoutStorageKey]);

  const showVideo =
    layout === "video-primary" || layout === "split" || tab !== "map";
  const showMapPane = tab === "map";
  const mapHeight =
    layout === "map-primary"
      ? mapPrimaryHeight
      : layout === "split"
        ? Math.round(mapPrimaryHeight * 0.55)
        : 360;
  const videoHeight = layout === "map-primary" ? 140 : layout === "split" ? 240 : 360;

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: 3,
        borderColor: "divider",
        width: "100%",
        alignSelf: "stretch",
        flexShrink: 0,
      }}
    >
      <StackHeader
        layout={layout}
        onLayoutChange={setLayout}
      />

      {tab === "map" && layout === "map-primary" ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <Box sx={{ minHeight: mapHeight, "& > *": { minHeight: mapHeight } }}>{map}</Box>
          <Box
            sx={{
              maxHeight: videoHeight,
              overflow: "hidden",
              "& [data-mission-video-frame]": { height: `${videoHeight}px !important`, minHeight: `${videoHeight}px !important` },
            }}
          >
            {video}
          </Box>
        </Box>
      ) : null}

      {tab === "map" && layout === "video-primary" ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <Box>{video}</Box>
          <Box sx={{ minHeight: mapHeight, "& > *": { minHeight: mapHeight } }}>{map}</Box>
        </Box>
      ) : null}

      {tab === "map" && layout === "split" ? (
        <Box
          sx={{
            display: "grid",
            gap: 1.5,
            gridTemplateColumns: { xs: "1fr", md: "1.4fr 1fr" },
            alignItems: "stretch",
          }}
        >
          <Box sx={{ minHeight: mapHeight, "& > *": { minHeight: mapHeight } }}>{map}</Box>
          <Box
            sx={{
              "& [data-mission-video-frame]": {
                height: `${videoHeight}px !important`,
                minHeight: `${videoHeight}px !important`,
              },
            }}
          >
            {video}
          </Box>
        </Box>
      ) : null}

      {/* Non-map tabs: keep video available for monitoring while configuring */}
      {tab !== "map" && showVideo ? <Box sx={{ mb: 1.5 }}>{video}</Box> : null}

      <Tabs
        value={tab}
        onChange={(_, next: SurveyTab) => setTab(next)}
        sx={{ mt: showMapPane ? 1.5 : 0, mb: 1, minHeight: 36, borderBottom: 1, borderColor: "divider" }}
        variant="scrollable"
        scrollButtons="auto"
      >
        <Tab label="Map" value="map" sx={{ minHeight: 36, py: 0.5 }} />
        <Tab label="Setup" value="setup" sx={{ minHeight: 36, py: 0.5 }} />
        {hasVideoAnalysis ? (
          <Tab label="Video Analysis" value="video-analysis" sx={{ minHeight: 36, py: 0.5 }} />
        ) : null}
      </Tabs>

      {tab === "setup" ? (
        <Box sx={{ pt: 0.5 }}>
          {setupSubtitle ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
              {setupSubtitle}
            </Typography>
          ) : null}
          {setup}
        </Box>
      ) : null}

      {tab === "video-analysis" && hasVideoAnalysis ? (
        <Box sx={{ pt: 0.5 }}>
          {videoAnalysisSubtitle ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
              {videoAnalysisSubtitle}
            </Typography>
          ) : null}
          {videoAnalysis}
        </Box>
      ) : null}
    </Paper>
  );
}

function StackHeader({
  layout,
  onLayoutChange,
}: {
  layout: SurveyLayoutMode;
  onLayoutChange: (mode: SurveyLayoutMode) => void;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 1,
        mb: 1,
        flexWrap: "wrap",
      }}
    >
      <Typography variant="caption" color="text.secondary">
        Workspace layout
      </Typography>
      <ToggleButtonGroup
        size="small"
        exclusive
        value={layout}
        onChange={(_, next: SurveyLayoutMode | null) => {
          if (next) onLayoutChange(next);
        }}
        aria-label="Survey workspace layout"
      >
        {(Object.keys(LAYOUT_LABELS) as SurveyLayoutMode[]).map((mode) => (
          <ToggleButton key={mode} value={mode} aria-label={LAYOUT_LABELS[mode]}>
            {LAYOUT_LABELS[mode]}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
    </Box>
  );
}
