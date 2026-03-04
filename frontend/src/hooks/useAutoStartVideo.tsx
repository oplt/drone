import { useEffect, useRef, useState } from "react";

export function useAutoStartVideo({
  apiBase,
  getToken,
  enabled,
  onError,
  resetKey,
}: {
  apiBase: string;
  getToken: () => string | null;
  enabled: boolean;
  onError: (msg: string) => void;
  resetKey?: string;
}) {
  const [starting, setStarting] = useState(false);
  const [streamKey, setStreamKey] = useState<number>(0);
  const startedRef = useRef(false);

  useEffect(() => {
    startedRef.current = false;
  }, [resetKey]);

  useEffect(() => {
    if (!enabled) return;
    if (startedRef.current) return;

    const token = getToken();
    if (!token) return;

    const timer = setTimeout(() => {
      setStarting(true);

      fetch(`${apiBase}/video/start`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (res) => {
          if (!res.ok) {
            let detail = `HTTP ${res.status}`;
            try {
              const data = (await res.json()) as { detail?: string };
              if (data?.detail) detail = data.detail;
            } catch {}
            throw new Error(detail);
          }
          setStreamKey(Date.now());
          startedRef.current = true;
        })
        .catch((e) => onError(`Failed to start video: ${e instanceof Error ? e.message : "Unknown error"}`))
        .finally(() => setStarting(false));
    }, 1000);

    return () => clearTimeout(timer);
  }, [apiBase, enabled, getToken, onError]);

  return { startingVideo: starting, streamKey };
}
