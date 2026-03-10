/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getToken } from "../auth";
import useTelemetryWebSocket from "../hooks/useTelemetryWebsocket";

export type AlertItem = {
  id: number;
  rule_type: string;
  dedupe_key: string;
  source: string;
  severity: string;
  status: string;
  title: string;
  message: string;
  meta_data: Record<string, unknown>;
  first_triggered_at: string;
  last_triggered_at: string;
  last_notified_at?: string | null;
  resolved_at?: string | null;
  acknowledged_at?: string | null;
  acknowledged_by_user_id?: number | null;
  occurrences: number;
  created_at: string;
  updated_at: string;
};

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

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

const parseApiError = async (res: Response, fallback: string): Promise<string> => {
  try {
    const text = await res.text();
    if (!text.trim()) {
      return `${fallback} (${res.status})`;
    }
    const parsed = JSON.parse(text);
    if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
    return text;
  } catch {
    return `${fallback} (${res.status})`;
  }
};

const sortAlerts = (items: AlertItem[]) => {
  return [...items].sort((a, b) => {
    const aTs = new Date(a.last_triggered_at).getTime();
    const bTs = new Date(b.last_triggered_at).getTime();
    return bTs - aTs;
  });
};

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
    const res = await fetch(`${API_BASE}/api/alerts/open-count`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      throw new Error(await parseApiError(res, "Failed to fetch open alert count"));
    }
    const data = (await res.json()) as { open_count?: number };
    setOpenCount(Number.isFinite(data?.open_count) ? Number(data.open_count) : 0);
  }, [token]);

  const fetchAlerts = useCallback(async () => {
    if (!token) {
      setAlerts([]);
      return;
    }
    const res = await fetch(`${API_BASE}/api/alerts?status=active&limit=50`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      throw new Error(await parseApiError(res, "Failed to fetch alerts"));
    }
    const data = (await res.json()) as { items?: AlertItem[] };
    setAlerts(sortAlerts(Array.isArray(data?.items) ? data.items : []));
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
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to acknowledge alert"));
      }
      const updated = (await res.json()) as AlertItem;
      setAlerts((prev) => upsertAlert(prev, updated));
      await fetchOpenCount();
    },
    [fetchOpenCount, token],
  );

  const resolveAlert = useCallback(
    async (alertId: number) => {
      if (!token) return;
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/resolve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to resolve alert"));
      }
      const updated = (await res.json()) as AlertItem;
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

  useTelemetryWebSocket({
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

  return (
    <AlertCenterContext.Provider value={value}>
      {children}
    </AlertCenterContext.Provider>
  );
}

export function useAlertCenter(): AlertCenterContextValue {
  const value = useContext(AlertCenterContext);
  if (!value) {
    throw new Error("useAlertCenter must be used inside AlertCenterProvider.");
  }
  return value;
}
