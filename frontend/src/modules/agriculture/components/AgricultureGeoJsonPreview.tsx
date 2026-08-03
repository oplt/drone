import { Box, Button, Chip, Stack, Typography } from "@mui/material";
import { useRef } from "react";

type Feature = {
  geometry?: { type?: string; coordinates?: unknown };
  properties?: Record<string, unknown>;
};

function coordinatePairs(value: unknown, result: number[][] = []): number[][] {
  if (
    Array.isArray(value) &&
    value.length >= 2 &&
    value.every((item) => typeof item === "number")
  ) {
    result.push([Number(value[0]), Number(value[1])]);
    return result;
  }
  if (Array.isArray(value))
    value.forEach((item) => coordinatePairs(item, result));
  return result;
}

function pathForCoordinates(
  value: unknown,
  project: (pair: number[]) => string,
): string {
  if (!Array.isArray(value)) return "";
  const rings =
    Array.isArray(value[0]) && Array.isArray(value[0][0]) ? value : [value];
  return (rings as unknown[])
    .map((ring) => {
      const points = coordinatePairs(ring).map(project);
      return points.length ? `M ${points.join(" L ")} Z` : "";
    })
    .join(" ");
}

function severityLabel(value: unknown): string {
  const severity = Number(value ?? 0.5);
  return severity >= 0.67
    ? "High severity"
    : severity >= 0.34
      ? "Medium severity"
      : "Low severity";
}

export function AgricultureGeoJsonPreview({
  geojson,
  selectedId,
  onSelect,
}: {
  geojson: { features?: Array<Record<string, unknown>> };
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const listRef = useRef<HTMLUListElement>(null);
  const features = (geojson.features ?? []) as Feature[];
  const pairs = features.flatMap((feature) =>
    coordinatePairs(feature.geometry?.coordinates),
  );
  if (!pairs.length)
    return (
      <Box sx={{ p: 2, bgcolor: "action.hover", borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary">
          No georeferenced features in this layer. Unresolved observations
          remain available in the review list.
        </Typography>
      </Box>
    );
  const xs = pairs.map((pair) => pair[0]);
  const ys = pairs.map((pair) => pair[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const dx = Math.max(maxX - minX, 0.00001);
  const dy = Math.max(maxY - minY, 0.00001);
  const project = (pair: number[]) =>
    `${((pair[0] - minX) / dx) * 360 + 20},${220 - ((pair[1] - minY) / dy) * 180}`;
  const moveListFocus = (index: number, direction: number) => {
    const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>(
      "button[data-map-feature]",
    );
    if (!buttons?.length) return;
    buttons[(index + direction + buttons.length) % buttons.length]?.focus();
  };
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" spacing={0.75} alignItems="center">
        <Typography variant="caption" color="text.secondary">
          Geospatial layer preview · auto-fit bounds
        </Typography>
        <Chip
          size="small"
          variant="outlined"
          label={`${features.length} features`}
        />
      </Stack>
      <Stack
        component="aside"
        aria-label="Map severity legend"
        direction="row"
        spacing={1.5}
        flexWrap="wrap"
        useFlexGap
      >
        <Typography variant="caption">
          <span aria-hidden="true">○</span> Low severity
        </Typography>
        <Typography variant="caption">
          <span aria-hidden="true">◐</span> Medium severity
        </Typography>
        <Typography variant="caption">
          <span aria-hidden="true">●</span> High severity
        </Typography>
        <Typography variant="caption">
          <span aria-hidden="true">▣</span> Selected feature
        </Typography>
      </Stack>
      <Box
        component="svg"
        viewBox="0 0 400 240"
        role="img"
        aria-label="Agriculture analysis map layer"
        sx={{
          width: "100%",
          minHeight: 180,
          bgcolor: "#eef4e9",
          borderRadius: 1,
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        <rect x="0" y="0" width="400" height="240" fill="#eef4e9" />
        {features.map((feature, index) => {
          const id = String(
            feature.properties?.observation_id ??
              feature.properties?.id ??
              index,
          );
          const selected = id === selectedId;
          const geometryType = feature.geometry?.type ?? "";
          const severity = Number(feature.properties?.severity ?? 0.5);
          const fill = selected
            ? "#d32f2f"
            : `rgba(25, 118, 210, ${0.25 + Math.min(0.7, severity * 0.7)})`;
          return geometryType === "Point" ? (
            <circle
              key={id}
              cx={
                project(
                  coordinatePairs(feature.geometry?.coordinates)[0] ?? [
                    minX,
                    minY,
                  ],
                ).split(",")[0]
              }
              cy={
                project(
                  coordinatePairs(feature.geometry?.coordinates)[0] ?? [
                    minX,
                    minY,
                  ],
                ).split(",")[1]
              }
              r={selected ? 7 : 5}
              fill={fill}
              stroke="#f8fafc"
              strokeWidth="2"
              aria-hidden="true"
            />
          ) : (
            <path
              key={id}
              d={pathForCoordinates(feature.geometry?.coordinates, project)}
              fill={fill}
              stroke={selected ? "#b71c1c" : "#1976d2"}
              strokeWidth={selected ? 3 : 1.5}
              aria-hidden="true"
            />
          );
        })}
      </Box>
      <Stack
        component="ul"
        ref={listRef}
        aria-label="Map feature review list"
        aria-describedby="map-keyboard-help"
        spacing={0.5}
        sx={{ listStyle: "none", p: 0, m: 0 }}
      >
        <Typography
          component="li"
          id="map-keyboard-help"
          variant="caption"
          color="text.secondary"
        >
          Use Tab to enter the list, then Up and Down Arrow keys to move between
          map features.
        </Typography>
        {features.map((feature, index) => {
          const id = String(
            feature.properties?.observation_id ??
              feature.properties?.id ??
              index,
          );
          const label = String(
            feature.properties?.observation_type ?? "Map feature",
          ).replaceAll("_", " ");
          const severity = severityLabel(feature.properties?.severity);
          const isCluster = feature.properties?.cluster === true;
          const count = isCluster ? Number(feature.properties?.count ?? 0) : 0;
          return (
            <li key={`list-${id}`}>
              <Button
                disableRipple
                size="small"
                fullWidth
                variant={id === selectedId ? "contained" : "text"}
                onClick={() => onSelect?.(id)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown" || event.key === "ArrowRight") {
                    event.preventDefault();
                    moveListFocus(index, 1);
                  }
                  if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
                    event.preventDefault();
                    moveListFocus(index, -1);
                  }
                }}
                data-map-feature
                aria-current={id === selectedId ? "true" : undefined}
                aria-label={`Select ${isCluster ? `${count} clustered ${label}s` : label} ${id}, ${severity}`}
                sx={{
                  justifyContent: "flex-start",
                  textTransform: "none",
                  minHeight: 44,
                }}
              >
                <span aria-hidden="true">
                  {severity.startsWith("High")
                    ? "●"
                    : severity.startsWith("Medium")
                      ? "◐"
                      : "○"}
                </span>
                &nbsp;{isCluster ? `${count} clustered features` : label} · {severity} · {id}
              </Button>
            </li>
          );
        })}
      </Stack>
    </Stack>
  );
}
