import { useEffect, useRef, useState } from "react";
import { getSessionMarker } from "../../session";
import { startVideoStream } from "../api/videoApi";
import { ApiError } from "../../../shared/api/apiError";

export function useMissionVideo({
  enabled,
  onError,
  resetKey,
}: {
  enabled: boolean;
  onError: (message: string) => void;
  resetKey?: string;
}) {
  const [starting, setStarting] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
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

    const token = getSessionMarker();
    if (!token) return;

    const controller = new AbortController();
    abortRef.current = controller;

    const timer = window.setTimeout(() => {
      startingRef.current = true;
      setStarting(true);

      startVideoStream(token)
        .then(() => {
          if (controller.signal.aborted) return;
          startedRef.current = true;
          setStreamKey(Date.now());
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          const detail =
            error instanceof ApiError
              ? error.message
              : error instanceof Error
                ? error.message
                : "Unknown error";
          onError(`Failed to start video: ${detail}`);
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
  }, [enabled, onError]);

  return { startingVideo: starting, streamKey };
}

export default useMissionVideo;
