import { useEffect, useMemo, useRef, useState } from "react";
import type { Cesium3DTileset } from "cesium";
import {
  Alert,
  Box,
  Checkbox,
  Chip,
  CircularProgress,
  FormControlLabel,
  Tooltip,
  Stack,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { fetchSignedTilesetUrl } from "../api/warehouseMapsApi";
import { getWarehouseName } from "../scannedMapSelectors";
import type { WarehouseScannedMapResponse } from "../types/missions";

type LayerState = {
  mesh: boolean;
  pointCloud: boolean;
  scanPath: boolean;
  footprint: boolean;
};

type ViewerStatus = "empty" | "loading" | "ready" | "error";

function absoluteAssetUrl(apiBase: string, rawUrl: string): string {
  if (/^https?:\/\//i.test(rawUrl)) return rawUrl;
  const normalizedPath = rawUrl.startsWith("/") ? rawUrl : `/${rawUrl}`;
  return `${apiBase}${normalizedPath}`;
}

function tilesetJsonUrl(rawUrl: string): string {
  if (/\.json(\?|$)/i.test(rawUrl)) return rawUrl;
  return `${rawUrl.replace(/\/+$/, "")}/tileset.json`;
}

function assetUrl(
  map: WarehouseScannedMapResponse | null,
  type: string,
): string | null {
  return map?.assets.find((asset) => asset.type === type)?.url ?? null;
}

function statusColor(
  status: string,
): "success" | "warning" | "error" | "default" {
  if (status === "ready") return "success";
  if (status === "failed") return "error";
  if (status === "processing" || status === "queued") return "warning";
  return "default";
}

export function WarehouseScanViewer({
  apiBase,
  getToken,
  map,
}: {
  apiBase: string;
  getToken: () => string | null;
  map: WarehouseScannedMapResponse | null;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState<ViewerStatus>("empty");
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerState>({
    mesh: true,
    pointCloud: true,
    scanPath: true,
    footprint: true,
  });

  const tilesetAsset = useMemo(
    () => map?.assets.find((asset) => asset.type === "TILESET_3D") ?? null,
    [map],
  );
  const pointCloud = assetUrl(map, "POINT_CLOUD");
  const scanPath = assetUrl(map, "SCAN_PATH");
  const footprint = assetUrl(map, "FOOTPRINT");
  const quality =
    map?.assets.find((asset) => asset.type === "QUALITY_REPORT") ?? null;
  const qualityReport = quality?.meta_data ?? {};
  const coverage =
    typeof qualityReport.coverage_percent === "number"
      ? qualityReport.coverage_percent
      : null;
  const drift =
    typeof qualityReport.drift_estimate_m === "number"
      ? qualityReport.drift_estimate_m
      : null;
  const availableLayers = {
    mesh: Boolean(tilesetAsset),
    pointCloud: Boolean(pointCloud),
    scanPath: Boolean(scanPath),
    footprint: Boolean(footprint),
  };

  useEffect(() => {
    let cancelled = false;
    cleanupRef.current?.();
    cleanupRef.current = null;
    setError(null);

    if (!map || !tilesetAsset || !layers.mesh) {
      setStatus(map ? "ready" : "empty");
      return () => {
        cancelled = true;
      };
    }

    setStatus("loading");
    void (async () => {
      const Cesium = await import("cesium");
      const token = getToken();
      let url: string | null = null;
      if (token) {
        url = await fetchSignedTilesetUrl(tilesetAsset.id, token).catch(
          () => null,
        );
      }
      url = url ?? tilesetJsonUrl(absoluteAssetUrl(apiBase, tilesetAsset.url));
      if (cancelled || !hostRef.current) return;

      const viewer = new Cesium.Viewer(hostRef.current, {
        animation: false,
        baseLayerPicker: false,
        fullscreenButton: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        selectionIndicator: false,
        timeline: false,
        navigationHelpButton: false,
        infoBox: false,
      });
      viewer.scene.globe.show = false;
      const tileset =
        typeof Cesium.Cesium3DTileset.fromUrl === "function"
          ? await Cesium.Cesium3DTileset.fromUrl(url)
          : new (Cesium.Cesium3DTileset as unknown as {
              new (options: { url: string }): Cesium3DTileset;
            })({ url });
      viewer.scene.primitives.add(tileset);
      await viewer.zoomTo(tileset);
      if (cancelled) {
        viewer.destroy();
        return;
      }
      cleanupRef.current = () => viewer.destroy();
      setStatus("ready");
    })().catch((err: unknown) => {
      if (!cancelled) {
        setStatus("error");
        setError(
          err instanceof Error ? err.message : "3D map could not be loaded.",
        );
      }
    });

    return () => {
      cancelled = true;
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, [apiBase, getToken, layers.mesh, map, tilesetAsset]);

  const toggleLayer = (key: keyof LayerState) => {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  };

  return (
    <Stack spacing={1.25}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
      >
        <Typography variant="subtitle1">
          <InfoLabel
            label="Warehouse 3D Map"
            info="Select a stored scan below to view mesh, point cloud, and path layers."
          />
        </Typography>
        <Stack direction="row" spacing={0.75} alignItems="center">
          {status === "loading" && <CircularProgress size={16} />}
          {map && (
            <Chip
              size="small"
              label={map.status}
              color={statusColor(map.status)}
            />
          )}
          {typeof map?.progress === "number" && (
            <Chip size="small" variant="outlined" label={`${map.progress}%`} />
          )}
        </Stack>
      </Stack>

      <Box
        ref={hostRef}
        sx={{
          height: 420,
          borderRadius: 1,
          overflow: "hidden",
          bgcolor: "rgba(0,0,0,0.88)",
          border: "1px solid",
          borderColor: "divider",
          position: "relative",
        }}
      >
        {(status === "empty" || (!tilesetAsset && !pointCloud)) && (
          <ViewerOverlay
            title="No 3D tiles yet"
            body="Select a ready scan with map assets."
          />
        )}
        {status === "loading" && (
          <ViewerOverlay title="Loading 3D map" body="Opening tileset." />
        )}
        {status === "error" && (
          <ViewerOverlay title="Map load failed" body={error ?? ""} />
        )}
        {!tilesetAsset && pointCloud && (
          <ViewerOverlay
            title="Point cloud available"
            body={absoluteAssetUrl(apiBase, pointCloud)}
          />
        )}
      </Box>

      {map?.error && <Alert severity="error">{map.error}</Alert>}

      <Stack direction="row" spacing={1} flexWrap="wrap">
        <Tooltip title="Estimated scanned surface coverage">
          <Chip
            size="small"
            color={coverage != null ? "success" : "default"}
            label={`coverage ${coverage?.toFixed(0) ?? "--"}%`}
          />
        </Tooltip>
        <Tooltip title="Estimated mapping drift">
          <Chip
            size="small"
            color={(drift ?? 0) > 0.5 ? "warning" : "success"}
            label={`drift ${drift?.toFixed(2) ?? "--"}m`}
          />
        </Tooltip>
        <Tooltip title="Mesh asset availability">
          <Chip
            size="small"
            color={tilesetAsset ? "success" : "warning"}
            label={tilesetAsset ? "mesh" : "missing mesh"}
          />
        </Tooltip>
        <Tooltip title="Point-cloud asset availability">
          <Chip
            size="small"
            color={pointCloud ? "success" : "warning"}
            label={pointCloud ? "point cloud" : "missing point cloud"}
          />
        </Tooltip>
        {(["mesh", "pointCloud", "scanPath", "footprint"] as const).map(
          (key) => (
            <Tooltip
              key={key}
              title={
                availableLayers[key]
                  ? "Toggle layer"
                  : "Layer asset not available for this scan"
              }
            >
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={layers[key]}
                    disabled={!availableLayers[key]}
                    onChange={() => toggleLayer(key)}
                  />
                }
                label={key.replace(
                  /[A-Z]/g,
                  (letter) => ` ${letter.toLowerCase()}`,
                )}
              />
            </Tooltip>
          ),
        )}
      </Stack>

      {map && (
        <Typography variant="caption" color="text.secondary">
          {`${getWarehouseName(map)} · v${map.model_version} · ${map.assets.length} assets${quality ? " · quality report" : ""}`}
        </Typography>
      )}
    </Stack>
  );
}

function ViewerOverlay({ title, body }: { title: string; body: string }) {
  return (
    <Box
      sx={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        color: "common.white",
        textAlign: "center",
        px: 3,
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography
        variant="caption"
        sx={{ opacity: 0.72, wordBreak: "break-all" }}
      >
        {body}
      </Typography>
    </Box>
  );
}
