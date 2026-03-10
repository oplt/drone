import { useEffect, type MutableRefObject } from "react";
import {
  TerraDraw,
  TerraDrawCircleMode,
  TerraDrawFreehandMode,
  TerraDrawLineStringMode,
  TerraDrawPointMode,
  TerraDrawPolygonMode,
  TerraDrawRectangleMode,
  TerraDrawSelectMode,
} from "terra-draw";
import { TerraDrawGoogleMapsAdapter } from "terra-draw-google-maps-adapter";

export type TerraDrawEditorMode =
  | "polygon"
  | "linestring"
  | "point"
  | "rectangle"
  | "circle"
  | "freehand"
  | "select"
  | "static";
export type TerraDrawToolMode = Exclude<TerraDrawEditorMode, "static">;

export type TerraDrawFeature = {
  id?: string | number;
  properties?: Record<string, unknown>;
  geometry?: {
    type?: string;
    coordinates?: unknown;
  };
};

type TerraDrawControllerProps = {
  map: google.maps.Map | null;
  enabled: boolean;
  mode: TerraDrawEditorMode;
  drawRef: MutableRefObject<TerraDraw | null>;
  onReadyChange: (ready: boolean) => void;
  onSnapshotChange: (snapshot: TerraDrawFeature[]) => void;
  onError?: (message: string) => void;
};

const SNAPSHOT_CHANGE_EVENTS = new Set([
  "create",
  "update",
  "delete",
  "created",
  "updated",
  "deleted",
]);

const stopTerraDraw = (
  drawRef: MutableRefObject<TerraDraw | null>,
  onReadyChange: (ready: boolean) => void
) => {
  if (!drawRef.current) return;
  drawRef.current.stop();
  drawRef.current = null;
  onReadyChange(false);
};

export function TerraDrawController({
  map,
  enabled,
  mode,
  drawRef,
  onReadyChange,
  onSnapshotChange,
  onError,
}: TerraDrawControllerProps) {
  useEffect(() => {
    if (enabled && map) return;
    stopTerraDraw(drawRef, onReadyChange);
  }, [drawRef, enabled, map, onReadyChange]);

  useEffect(() => {
    if (!enabled || !map || drawRef.current) return;

    let projectionListener: google.maps.MapsEventListener | null = null;

    // Wait until Google Maps projection is available before initializing TerraDraw.
    const initializeTerraDraw = () => {
      if (drawRef.current) return;

      try {
        const adapter = new TerraDrawGoogleMapsAdapter({
          map,
          lib: google.maps,
          coordinatePrecision: 9,
        });

        const draw = new TerraDraw({
          adapter,
          modes: [
            new TerraDrawSelectMode({
              flags: {
                polygon: {
                  feature: {
                    draggable: true,
                    coordinates: { draggable: true, deletable: true, midpoints: true },
                  },
                },
                linestring: {
                  feature: {
                    draggable: true,
                    coordinates: { draggable: true, deletable: true, midpoints: true },
                  },
                },
                point: { feature: { draggable: true } },
              },
            }),
            new TerraDrawPolygonMode({
              editable: true,
              showCoordinatePoints: false,
              styles: {
                fillColor: "#000000",
                fillOpacity: 0.1,
                outlineColor: "#1976d2",
                closingPointWidth: 0,
                closingPointOutlineWidth: 0,
                coordinatePointWidth: 0,
                coordinatePointOutlineWidth: 0,
              },
            }),
            new TerraDrawLineStringMode({
              editable: true,
              showCoordinatePoints: false,
              styles: {
                lineStringColor: "#1976d2",
                closingPointWidth: 0,
                closingPointOutlineWidth: 0,
                coordinatePointWidth: 0,
                coordinatePointOutlineWidth: 0,
              },
            }),
            new TerraDrawPointMode({
              editable: true,
              styles: { pointColor: "#1976d2" },
            }),
            new TerraDrawRectangleMode({
              styles: { fillColor: "#000000", fillOpacity: 0.1, outlineColor: "#1976d2" },
            }),
            new TerraDrawCircleMode({
              styles: { fillColor: "#000000", fillOpacity: 0.1, outlineColor: "#1976d2" },
            }),
            new TerraDrawFreehandMode({
              styles: { fillColor: "#000000", fillOpacity: 0.1, outlineColor: "#1976d2" },
            }),
          ],
        });

        draw.on("change", (_ids: Array<string | number>, event: string) => {
          if (!SNAPSHOT_CHANGE_EVENTS.has(event)) return;
          onSnapshotChange(draw.getSnapshot() as TerraDrawFeature[]);
        });

        draw.start();
        draw.setMode(mode);
        drawRef.current = draw;
        onReadyChange(true);
        projectionListener?.remove();
        projectionListener = null;
      } catch (error) {
        console.error("Failed to initialize TerraDraw:", error);
        onError?.("Failed to initialize drawing tools");
      }
    };

    projectionListener = map.addListener("projection_changed", initializeTerraDraw);
    if (map.getProjection()) initializeTerraDraw();

    return () => {
      projectionListener?.remove();
      projectionListener = null;
    };
  }, [drawRef, enabled, map, mode, onError, onReadyChange, onSnapshotChange]);

  useEffect(() => {
    if (!enabled || !drawRef.current) return;
    drawRef.current.setMode(mode);
  }, [drawRef, enabled, mode]);

  useEffect(() => {
    return () => {
      stopTerraDraw(drawRef, onReadyChange);
    };
  }, [drawRef, onReadyChange]);

  return null;
}
