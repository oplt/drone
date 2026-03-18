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
  const startingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    startedRef.current = false;
    startingRef.current = false;
    setStarting(false);
    abortRef.current?.abort();
    abortRef.current = null;
  }, [resetKey]);

  useEffect(() => {
    if (!enabled) {
      abortRef.current?.abort();
      abortRef.current = null;
      setStarting(false);
      startingRef.current = false;
      return;
    }

    if (startedRef.current || startingRef.current) return;

    const token = getToken();
    if (!token) return;

    const controller = new AbortController();
    abortRef.current = controller;

    const timer = window.setTimeout(() => {
      startingRef.current = true;
      setStarting(true);

      fetch(`${apiBase}/video/start`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      })
        .then(async (res) => {
          if (!res.ok) {
            let detail = `HTTP ${res.status}`;
            try {
              const data = (await res.json()) as { detail?: string };
              if (data?.detail) detail = data.detail;
            } catch {
              // ignore
            }
            throw new Error(detail);
          }

          startedRef.current = true;
          setStreamKey(Date.now());
        })
        .catch((e) => {
          if (controller.signal.aborted) return;
          onError(
            `Failed to start video: ${e instanceof Error ? e.message : "Unknown error"}`,
          );
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setStarting(false);
          }
          startingRef.current = false;
        });
    }, 400);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    };
  }, [apiBase, enabled, getToken, onError]);

  return { startingVideo: starting, streamKey };
}