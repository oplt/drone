/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getToken } from "../../session";
import { useTelemetryStream } from "../../mission-runtime";
import { frontendLogger } from "../../../shared/logging";
import {
  acknowledgeAlert as acknowledgeAlertApi,
  fetchActiveAlerts,
  fetchOpenAlertCount,
  resolveAlert as resolveAlertApi,
} from "../api/alertsApi";
import type { AlertItem } from "../types";

export type { AlertItem };

type AlertCenterContextValue = {
  alerts: AlertItem[];
  openCount: number;
  loading: boolean;
  /** Last failed fetch message; null when last load succeeded. */
  loadError: string | null;
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
  refresh: () => Promise<void>;
  acknowledgeAlert: (alertId: number) => Promise<void>;
  resolveAlert: (alertId: number) => Promise<void>;
};

const AlertCenterContext = createContext<AlertCenterContextValue | null>(null);

const SEVERITY_RANK: Record<string, number> = {
  critical: 0,
  error: 0,
  high: 1,
  medium: 2,
  warning: 2,
  low: 3,
  info: 3,
};

const sortAlerts = (items: AlertItem[]) =>
  [...items].sort((a, b) => {
    const bySev =
      (SEVERITY_RANK[String(a.severity).toLowerCase()] ?? 4) -
      (SEVERITY_RANK[String(b.severity).toLowerCase()] ?? 4);
    if (bySev !== 0) return bySev;
    return new Date(b.last_triggered_at).getTime() - new Date(a.last_triggered_at).getTime();
  });

const upsertAlert = (items: AlertItem[], incoming: AlertItem): AlertItem[] => {
  const next = items.filter((item) => item.id !== incoming.id);
  if (incoming.status !== "resolved") {
    next.push(incoming);
  }
  return sortAlerts(next);
};

function isAlertSocketMessage(value: unknown): value is { type: "alert_event"; alert: AlertItem } {
  return Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      "type" in value &&
      (value as { type?: unknown }).type === "alert_event" &&
      "alert" in value,
  );
}

export function AlertCenterProvider({ children }: { children: React.ReactNode }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const token = getToken();

  const fetchOpenCount = useCallback(async () => {
    if (!token) {
      setOpenCount(0);
      return;
    }
    setOpenCount(await fetchOpenAlertCount(token));
  }, [token]);

  const fetchAlerts = useCallback(async () => {
    if (!token) {
      setAlerts([]);
      return;
    }
    setAlerts(sortAlerts(await fetchActiveAlerts(token)));
  }, [token]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([fetchAlerts(), fetchOpenCount()]);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }, [fetchAlerts, fetchOpenCount]);

  const acknowledgeAlert = useCallback(
    async (alertId: number) => {
      if (!token) return;
      const updated = await acknowledgeAlertApi(alertId, token);
      setAlerts((prev) => upsertAlert(prev, updated));
      await fetchOpenCount();
    },
    [fetchOpenCount, token],
  );

  const resolveAlert = useCallback(
    async (alertId: number) => {
      if (!token) return;
      const updated = await resolveAlertApi(alertId, token);
      setAlerts((prev) => upsertAlert(prev, updated));
      await fetchOpenCount();
    },
    [fetchOpenCount, token],
  );

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setAlerts([]);
      setOpenCount(0);
      return;
    }

    setLoading(true);
    Promise.all([fetchAlerts(), fetchOpenCount()])
      .then(() => {
        if (!cancelled) setLoadError(null);
      })
      .catch((error) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : String(error);
          setLoadError(message);
          frontendLogger.warn("frontend", "Failed to initialize alert center", {
            error: message,
          });
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    // Alert events arrive on the shared telemetry stream. Refresh only when
    // returning to a visible tab; a fixed poll duplicated stream traffic and
    // made every dashboard instance hit both alert endpoints indefinitely.
    const refreshWhenVisible = () => {
      if (document.hidden || cancelled) return;
      void Promise.all([fetchAlerts(), fetchOpenCount()])
        .then(() => {
          if (!cancelled) setLoadError(null);
        })
        .catch((error) => {
          if (!cancelled) {
            const message = error instanceof Error ? error.message : String(error);
            setLoadError(message);
            frontendLogger.warn("frontend", "Failed to refresh alert center", {
              error: message,
            });
          }
        });
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [fetchAlerts, fetchOpenCount, token]);

  useTelemetryStream({
    enabled: Boolean(token),
    onMessage: (msg) => {
      if (!isAlertSocketMessage(msg)) {
        return;
      }
      setAlerts((prev) => upsertAlert(prev, msg.alert));
      void fetchOpenCount().catch((error) => {
        frontendLogger.warn("frontend", "Failed to refresh open alert count after event", {
          error: error instanceof Error ? error.message : String(error),
        });
      });
    },
  });

  const value = useMemo<AlertCenterContextValue>(
    () => ({
      alerts,
      openCount,
      loading,
      loadError,
      drawerOpen,
      setDrawerOpen,
      refresh,
      acknowledgeAlert,
      resolveAlert,
    }),
    [
      acknowledgeAlert,
      alerts,
      drawerOpen,
      loadError,
      loading,
      openCount,
      refresh,
      resolveAlert,
    ],
  );

  return <AlertCenterContext.Provider value={value}>{children}</AlertCenterContext.Provider>;
}

export function useAlertCenter(): AlertCenterContextValue {
  const value = useContext(AlertCenterContext);
  if (!value) {
    throw new Error("useAlertCenter must be used inside AlertCenterProvider.");
  }
  return value;
}
