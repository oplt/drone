/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getToken } from "../../session";
import { useTelemetryStream } from "../../mission-runtime";
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
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
  refresh: () => Promise<void>;
  acknowledgeAlert: (alertId: number) => Promise<void>;
  resolveAlert: (alertId: number) => Promise<void>;
};

const AlertCenterContext = createContext<AlertCenterContextValue | null>(null);

const sortAlerts = (items: AlertItem[]) =>
  [...items].sort(
    (a, b) => new Date(b.last_triggered_at).getTime() - new Date(a.last_triggered_at).getTime(),
  );

const upsertAlert = (items: AlertItem[], incoming: AlertItem): AlertItem[] => {
  const next = items.filter((item) => item.id !== incoming.id);
  if (incoming.status !== "resolved") {
    next.push(incoming);
  }
  return sortAlerts(next);
};

export function AlertCenterProvider({ children }: { children: React.ReactNode }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [loading, setLoading] = useState(false);
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
      .catch((error) => {
        if (!cancelled) {
          console.warn("Failed to initialize alert center:", error);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    const interval = window.setInterval(() => {
      void Promise.all([fetchAlerts(), fetchOpenCount()]).catch((error) => {
        if (!cancelled) {
          console.warn("Failed to refresh alerts:", error);
        }
      });
    }, 30000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [fetchAlerts, fetchOpenCount, token]);

  useTelemetryStream({
    enabled: Boolean(token),
    onMessage: (msg) => {
      if (!msg || msg.type !== "alert_event" || !msg.alert) {
        return;
      }
      setAlerts((prev) => upsertAlert(prev, msg.alert as AlertItem));
      void fetchOpenCount().catch((error) => {
        console.warn("Failed to refresh open alert count after event:", error);
      });
    },
  });

  const value = useMemo<AlertCenterContextValue>(
    () => ({
      alerts,
      openCount,
      loading,
      drawerOpen,
      setDrawerOpen,
      refresh,
      acknowledgeAlert,
      resolveAlert,
    }),
    [acknowledgeAlert, alerts, drawerOpen, loading, openCount, refresh, resolveAlert],
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
