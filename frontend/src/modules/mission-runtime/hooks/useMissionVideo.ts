import { useEffect, useRef, useState } from "react";
import { getSessionMarker } from "../../session";
import {
  fetchVideoStatus,
  startVideoStream,
  type VideoStreamStatus,
} from "../api/videoApi";
import { ApiError } from "../../../shared/api/apiError";

const INITIAL_POLL_DELAY_MS = 400;
const MAX_VIDEO_START_ATTEMPTS = 8;
const MAX_BACKOFF_MS = 60_000;

function backoffDelayMs(attempt: number, serverRetryAfterMs = 0): number {
  const exponential = Math.min(
    MAX_BACKOFF_MS,
    5_000 * 2 ** Math.max(0, attempt - 1),
  );
  return Math.max(exponential, serverRetryAfterMs);
}

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
  const [videoStatus, setVideoStatus] = useState<VideoStreamStatus | null>(
    null,
  );
  const attemptRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const retryTimerRef = useRef<number | null>(null);

  useEffect(() => {
    attemptRef.current = 0;
    setStarting(false);
    setVideoStatus(null);
    abortRef.current?.abort();
    abortRef.current = null;
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, [resetKey]);

  useEffect(() => {
    if (!enabled) {
      abortRef.current?.abort();
      abortRef.current = null;
      setStarting(false);
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      return;
    }

    const token = getSessionMarker();
    if (!token) return;

    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;

    const scheduleRetry = (delayMs: number) => {
      if (cancelled || controller.signal.aborted) return;
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current);
      }
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = null;
        if (!cancelled && !controller.signal.aborted) {
          void attemptStart();
        }
      }, delayMs);
    };

    const attemptStart = async () => {
      if (cancelled || controller.signal.aborted) return;
      if (attemptRef.current >= MAX_VIDEO_START_ATTEMPTS) {
        onError(
          "Video stream unavailable after repeated attempts. Retry manually when the camera is ready.",
        );
        setStarting(false);
        return;
      }

      attemptRef.current += 1;
      setStarting(true);

      try {
        const status = await fetchVideoStatus(token);
        if (cancelled || controller.signal.aborted) return;
        setVideoStatus(status);

        const retryAfterMs = Number(status.retry_after_ms ?? 0);
        if (retryAfterMs > 0) {
          scheduleRetry(backoffDelayMs(attemptRef.current, retryAfterMs));
          setStarting(false);
          return;
        }

        if (!status.first_frame_available) {
          await startVideoStream(token);
          if (cancelled || controller.signal.aborted) return;

          const warmed = await fetchVideoStatus(token);
          if (cancelled || controller.signal.aborted) return;
          setVideoStatus(warmed);

          const warmedRetryAfterMs = Number(warmed.retry_after_ms ?? 0);
          if (warmedRetryAfterMs > 0 || !warmed.first_frame_available) {
            scheduleRetry(
              backoffDelayMs(
                attemptRef.current,
                warmedRetryAfterMs || 5_000,
              ),
            );
            setStarting(false);
            return;
          }
        }

        attemptRef.current = 0;
        setStreamKey(Date.now());
      } catch (error) {
        if (cancelled || controller.signal.aborted) return;
        const detail =
          error instanceof ApiError
            ? error.message
            : error instanceof Error
              ? error.message
              : "Unknown error";
        scheduleRetry(backoffDelayMs(attemptRef.current));
        if (attemptRef.current >= MAX_VIDEO_START_ATTEMPTS) {
          onError(`Failed to start video: ${detail}`);
        }
      } finally {
        if (!cancelled && !controller.signal.aborted) {
          setStarting(false);
        }
      }
    };

    const initialTimer = window.setTimeout(() => {
      void attemptStart();
    }, INITIAL_POLL_DELAY_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(initialTimer);
      controller.abort();
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };
  }, [enabled, onError]);

  return { startingVideo: starting, streamKey, videoStatus };
}

export default useMissionVideo;
