import type * as Cesium from "cesium";
import { frontendLogger } from "../../../../shared/logging";

export async function loadCesiumFieldTileset(args: {
  CesiumModule: typeof Cesium;
  viewer: Cesium.Viewer;
  url: string | null;
  fieldTilesetRef: { current: Cesium.Cesium3DTileset | null };
  tilesetLoadSeqRef: { current: number };
  viewerRef: { current: Cesium.Viewer | null };
}) {
  const {
    CesiumModule,
    viewer,
    url,
    fieldTilesetRef,
    tilesetLoadSeqRef,
    viewerRef,
  } = args;

  const requestId = ++tilesetLoadSeqRef.current;

  if (fieldTilesetRef.current) {
    try {
      viewer.scene.primitives.remove(fieldTilesetRef.current);
    } catch {
      // ignore cleanup errors
    }
    fieldTilesetRef.current = null;
  }

  if (!url) return;

  let tilesetUrl = url.trim();
  if (!tilesetUrl) return;

  let tilesetUrlPointsToJson = /\.json(\?|$)/i.test(tilesetUrl);
  if (!tilesetUrlPointsToJson) {
    try {
      const parsed = new URL(tilesetUrl, window.location.origin);
      const signedAssetPath = parsed.searchParams.get("path")?.trim() ?? "";
      tilesetUrlPointsToJson =
        /\.json$/i.test(parsed.pathname) || /\.json$/i.test(signedAssetPath);
    } catch {
      tilesetUrlPointsToJson = false;
    }
  }
  if (!tilesetUrlPointsToJson) {
    tilesetUrl = `${tilesetUrl.replace(/\/$/, "")}/tileset.json`;
  }

  try {
    const tileset =
      typeof CesiumModule.Cesium3DTileset.fromUrl === "function"
        ? await CesiumModule.Cesium3DTileset.fromUrl(tilesetUrl, {
            maximumScreenSpaceError: 16,
          })
        : new (CesiumModule.Cesium3DTileset as any)({
            url: tilesetUrl,
            maximumScreenSpaceError: 16,
          });

    if (!viewerRef.current || requestId !== tilesetLoadSeqRef.current) {
      try {
        tileset.destroy();
      } catch {
        // ignore stale tileset cleanup errors
      }
      return;
    }

    viewer.scene.primitives.add(tileset);
    fieldTilesetRef.current = tileset;
  } catch (error) {
    frontendLogger.error("frontend", "Failed to load field 3D tileset", {
      message: error instanceof Error ? error.message : String(error),
    });
  }
}
