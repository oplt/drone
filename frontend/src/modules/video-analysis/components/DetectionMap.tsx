import { useEffect, useMemo, useRef } from "react";
import { Box, Card, CardContent, Typography } from "@mui/material";
import maplibregl, { Map as MapLibreInstance } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { VideoDetection } from "../types";

type Props = {
  detections: VideoDetection[];
  selected?: VideoDetection | null;
  onSelect: (detection: VideoDetection) => void;
};

export function DetectionMap({ detections, selected, onSelect }: Props) {
  const elementRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreInstance | null>(null);
  const latestLocatedRef = useRef<VideoDetection[]>([]);
  const onSelectRef = useRef(onSelect);
  const located = useMemo(
    () => detections.filter((detection) => detection.lat != null && detection.lon != null),
    [detections],
  );
  latestLocatedRef.current = located;
  onSelectRef.current = onSelect;
  const geojson = useMemo(() => ({
    type: "FeatureCollection" as const,
    features: located.map((detection) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [detection.lon as number, detection.lat as number] },
      properties: { id: detection.id, selected: detection.id === selected?.id },
    })),
  }), [located, selected]);

  const hasLocated = located.length > 0;
  useEffect(() => {
    if (!elementRef.current || mapRef.current || located.length === 0) return;
    const first = located[0];
    const map = new maplibregl.Map({
      container: elementRef.current,
      style: "https://tiles.stadiamaps.com/styles/alidade_smooth.json",
      center: [first.lon as number, first.lat as number],
      zoom: 14,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      map.addSource("detections", { type: "geojson", data: geojson });
      map.addLayer({
        id: "detections-circle",
        type: "circle",
        source: "detections",
        paint: { "circle-radius": ["case", ["get", "selected"], 9, 6], "circle-stroke-width": 2, "circle-stroke-color": "#fff", "circle-color": ["case", ["get", "selected"], "#ed6c02", "#1976d2"] },
      });
      map.on("click", "detections-circle", (event) => {
        const id = event.features?.[0]?.properties?.id as string | undefined;
        const detection = latestLocatedRef.current.find((entry) => entry.id === id);
        if (detection) onSelectRef.current(detection);
      });
    });
    return () => { map.remove(); mapRef.current = null; };
    // Initialize only when first located result becomes available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasLocated]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    (map.getSource("detections") as maplibregl.GeoJSONSource | undefined)?.setData(geojson);
    if (selected?.lat != null && selected.lon != null) {
      map.flyTo({ center: [selected.lon, selected.lat], zoom: Math.max(map.getZoom(), 16) });
    }
  }, [geojson, selected]);

  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>Detection map</Typography>
        {located.length === 0 ? (
          <Box sx={{ minHeight: 220, display: "grid", placeItems: "center", bgcolor: "action.hover", borderRadius: 1, p: 2 }}>
            <Typography variant="body2" color="text.secondary" textAlign="center">GPS-linked detections appear when source mission telemetry is available.</Typography>
          </Box>
        ) : (
          <Box ref={elementRef} sx={{ height: 360, borderRadius: 1, overflow: "hidden" }} />
        )}
      </CardContent>
    </Card>
  );
}
