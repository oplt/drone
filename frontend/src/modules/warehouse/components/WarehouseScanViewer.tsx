import { useEffect, useMemo, useRef, useState } from "react";
import type { Cesium3DTileset } from "cesium";
import {
  Alert,
  Box,
  Checkbox,
  Chip,
  CircularProgress,
  FormControlLabel,
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

function assetUrl(map: WarehouseScannedMapResponse | null, type: string): string | null {
  return map?.assets.find((asset) => asset.type === type)?.url ?? null;
}

function statusColor(status: string): "success" | "warning" | "error" | "default" {
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
  const quality = map?.assets.find((asset) => asset.type === "QUALITY_REPORT") ?? null;

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
        url = await fetchSignedTilesetUrl(tilesetAsset.id, token).catch(() => null);
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
        setError(err instanceof Error ? err.message : "3D map could not be loaded.");
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
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap">
        <Typography variant="subtitle1">
          <InfoLabel
            label="Warehouse 3D Map"
            info="Select a stored scan below to view mesh, point cloud, and path layers."
          />
        </Typography>
        <Stack direction="row" spacing={0.75} alignItems="center">
          {status === "loading" && <CircularProgress size={16} />}
          {map && <Chip size="small" label={map.status} color={statusColor(map.status)} />}
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
          <ViewerOverlay title="No 3D tiles yet" body="Select a ready scan with map assets." />
        )}
        {status === "loading" && <ViewerOverlay title="Loading 3D map" body="Opening tileset." />}
        {status === "error" && <ViewerOverlay title="Map load failed" body={error ?? ""} />}
        {!tilesetAsset && pointCloud && (
          <ViewerOverlay title="Point cloud available" body={absoluteAssetUrl(apiBase, pointCloud)} />
        )}
      </Box>

      {map?.error && <Alert severity="error">{map.error}</Alert>}

      <Stack direction="row" spacing={1} flexWrap="wrap">
        {(["mesh", "pointCloud", "scanPath", "footprint"] as const).map((key) => (
          <FormControlLabel
            key={key}
            control={
              <Checkbox
                size="small"
                checked={layers[key]}
                onChange={() => toggleLayer(key)}
              />
            }
            label={key.replace(/[A-Z]/g, (letter) => ` ${letter.toLowerCase()}`)}
          />
        ))}
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
      <Typography variant="caption" sx={{ opacity: 0.72, wordBreak: "break-all" }}>
        {body}
      </Typography>
    </Box>
  );
}
