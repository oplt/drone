import type { ReactNode } from "react";
import { useState } from "react";
import { Box, Paper, Tab, Tabs, Typography } from "@mui/material";

type SurveyTab = "map" | "setup" | "video-analysis";

type MissionSurveyCameraSectionProps = {
  video: ReactNode;
  map: ReactNode;
  setup: ReactNode;
  setupSubtitle?: string;
  videoAnalysis?: ReactNode;
  videoAnalysisSubtitle?: string;
};

export function MissionSurveyCameraSection({
  video,
  map,
  setup,
  setupSubtitle,
  videoAnalysis,
  videoAnalysisSubtitle = "Upload recorded flights and run offline YOLO detection.",
}: MissionSurveyCameraSectionProps) {
  const [tab, setTab] = useState<SurveyTab>("map");
  const hasVideoAnalysis = videoAnalysis != null;

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
      {video}

      <Tabs
        value={tab}
        onChange={(_, next: SurveyTab) => setTab(next)}
        sx={{ mt: 1.5, mb: 1, minHeight: 36, borderBottom: 1, borderColor: "divider" }}
        variant="scrollable"
        scrollButtons="auto"
      >
        <Tab label="Map" value="map" sx={{ minHeight: 36, py: 0.5 }} />
        <Tab label="Setup" value="setup" sx={{ minHeight: 36, py: 0.5 }} />
        {hasVideoAnalysis ? (
          <Tab label="Video Analysis" value="video-analysis" sx={{ minHeight: 36, py: 0.5 }} />
        ) : null}
      </Tabs>

      {tab === "map" ? <Box sx={{ minHeight: 0 }}>{map}</Box> : null}

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
