import { useEffect, useMemo, useState } from "react";
import { getToken } from "../../../modules/session";
import {
  fetchIrrigationMissionSummary,
  triggerIrrigationMissionProcessing,
} from "../api/irrigationApi";
import type { IrrigationMissionSummary } from "../types/irrigation";
import type { LatLng } from "../../../shared/utils/extractLatLng";

export type IrrigationZoneStyle = {
  fillColor: string;
  strokeColor: string;
  label: string;
};

export function useFieldSurveyIrrigation(trackedMissionId: string | null) {
  const [irrigationSummary, setIrrigationSummary] =
    useState<IrrigationMissionSummary | null>(null);
  const [irrigationLoading, setIrrigationLoading] = useState(false);
  const [irrigationRefreshing, setIrrigationRefreshing] = useState(false);
  const [irrigationError, setIrrigationError] = useState<string | null>(null);

  useEffect(() => {
    if (!trackedMissionId) {
      setIrrigationSummary(null);
      setIrrigationError(null);
      return;
    }

    const token = getToken();
    if (!token) return;
    let cancelled = false;

    const loadSummary = async (background: boolean) => {
      if (!background) setIrrigationLoading(true);
      setIrrigationRefreshing(background);
      try {
        const summary = await fetchIrrigationMissionSummary(trackedMissionId, token);
        if (!cancelled) {
          setIrrigationSummary(summary);
          setIrrigationError(null);
        }
      } catch (error: unknown) {
        if (!cancelled) {
          setIrrigationError(
            error instanceof Error
              ? error.message
              : "Failed to load irrigation outputs"
          );
        }
      } finally {
        if (!cancelled) {
          setIrrigationLoading(false);
          setIrrigationRefreshing(false);
        }
      }
    };

    void loadSummary(false);
    const timer = window.setInterval(() => {
      void loadSummary(true);
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [trackedMissionId]);

  const irrigationLayer = irrigationSummary?.layer ?? null;
  const irrigationZoneStyles = useMemo<Record<string, IrrigationZoneStyle>>(
    () => ({
      under_irrigated: {
        fillColor: "#d97706",
        strokeColor: "#92400e",
        label: "Dry zone",
      },
      overwatered: {
        fillColor: "#0284c7",
        strokeColor: "#075985",
        label: "Overwatered",
      },
      uneven_distribution: {
        fillColor: "#7c3aed",
        strokeColor: "#5b21b6",
        label: "Uneven band",
      },
    }),
    []
  );
  const irrigationZonePaths = useMemo(
    () =>
      (irrigationSummary?.anomaly_zones ?? [])
        .map((zone) => {
          const coords = zone?.polygon_geojson?.coordinates?.[0];
          if (!Array.isArray(coords) || coords.length < 4) return null;
          return {
            zone,
            path: coords.map((pair) => ({
              lng: Number(pair[0]),
              lat: Number(pair[1]),
            })),
          };
        })
        .filter(Boolean) as Array<{
        zone: IrrigationMissionSummary["anomaly_zones"][number];
        path: LatLng[];
      }>,
    [irrigationSummary]
  );
  const irrigationCapturePreview =
    irrigationSummary?.captures?.slice(0, 3) ?? [];
  const overlayBounds = irrigationLayer?.tile_manifest?.bounds ?? null;

  const reprocessIrrigation = async () => {
    const token = getToken();
    if (!token || !trackedMissionId) return;
    try {
      setIrrigationRefreshing(true);
      await triggerIrrigationMissionProcessing(trackedMissionId, token);
      const refreshed = await fetchIrrigationMissionSummary(trackedMissionId, token);
      setIrrigationSummary(refreshed);
      setIrrigationError(null);
    } catch (error: unknown) {
      setIrrigationError(
        error instanceof Error
          ? error.message
          : "Failed to run irrigation analysis"
      );
    } finally {
      setIrrigationRefreshing(false);
    }
  };

  const resetIrrigationOnMissionStart = () => {
    setIrrigationSummary(null);
    setIrrigationError(null);
  };

  return {
    irrigationSummary,
    irrigationLoading,
    irrigationRefreshing,
    irrigationError,
    irrigationLayer,
    irrigationZoneStyles,
    irrigationZonePaths,
    irrigationCapturePreview,
    overlayBounds,
    reprocessIrrigation,
    resetIrrigationOnMissionStart,
  };
}
