import { Chip, Stack, Typography } from "@mui/material";
import { useMemo } from "react";
import type { AgricultureChange } from "../types";
import { AgricultureAnalysisMap } from "./AgricultureAnalysisMap";

const EMPTY = { type: "FeatureCollection", features: [] };

export function AgricultureTemporalChangeMap({
  changes,
  selectedId,
  onSelect,
}: {
  changes: AgricultureChange[];
  selectedId?: string | null;
  onSelect: (id: string) => void;
}) {
  const geojson = useMemo(() => ({
    type: "FeatureCollection",
    features: changes.flatMap((change) => {
      const geometry = change.state === "resolved"
        ? change.reference_geometry_geojson
        : change.geometry_geojson;
      if (!geometry.type) return [];
      return [{
        type: "Feature",
        geometry,
        properties: {
          change_id: change.id,
          observation_type: change.observation_type,
          state: change.state,
          lifecycle: ["stable", "expanding", "improving"].includes(change.state)
            ? "persistent"
            : change.state,
          area_m2: change.area_m2,
          delta_area_m2: change.delta_area_m2,
          confidence: change.confidence,
        },
      }];
    }),
  }), [changes]);
  const newCount = changes.filter((change) => change.state === "new").length;
  const resolvedCount = changes.filter((change) => change.state === "resolved").length;
  const persistentCount = changes.length - newCount - resolvedCount;
  const areaDelta = changes.reduce((sum, change) => sum + (change.delta_area_m2 ?? 0), 0);

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap aria-label="Temporal change summary">
        <Chip size="small" color="error" label={`New ${newCount}`} />
        <Chip size="small" color="info" label={`Persistent ${persistentCount}`} />
        <Chip size="small" color="success" label={`Resolved ${resolvedCount}`} />
        <Chip size="small" variant="outlined" label={`Net area ${areaDelta >= 0 ? "+" : ""}${areaDelta.toFixed(1)} m²`} />
      </Stack>
      <AgricultureAnalysisMap
        observations={EMPTY}
        temporalChanges={geojson}
        selectedId={selectedId}
        onSelect={onSelect}
        height={380}
        initialVisibility={{ observations: false, severity: false, interventionZones: false }}
      />
      <Typography variant="caption" color="text.secondary">
        Resolved findings use the reference footprint; persistent includes stable, expanding and improving matches.
      </Typography>
    </Stack>
  );
}
