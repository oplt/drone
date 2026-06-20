import { useCallback, useEffect, useState } from "react";
import {
  useAutoStartVideo,
  useMissionWebsocketRuntime,
} from "../../mission-runtime";
import { getToken } from "../../session";
import type { WarehouseMissionStatus } from "../warehousePageSupport";

type RuntimeControllerOptions = {
  apiBase: string;
  onError: (message: string) => void;
};

export function useWarehouseMissionRuntimeController({
  apiBase,
  onError,
}: RuntimeControllerOptions) {
  const runtime = useMissionWebsocketRuntime<WarehouseMissionStatus>({
    apiBase,
    getTokenFn: getToken,
    onError,
    alwaysConnect: true,
  });
  const { activeFlightId, droneConnected, disconnect } = runtime;
  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase,
    getToken,
    enabled: Boolean(activeFlightId && droneConnected),
    onError,
    resetKey: activeFlightId ?? "none",
  });
  const [manualStreamKey, setManualStreamKey] = useState<{
    flightId: string | null;
    key: number;
  } | null>(null);
  const [videoErrorMessage, setVideoErrorMessage] = useState<string | null>(null);
  const [videoErrorStreamKey, setVideoErrorStreamKey] = useState<number | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);

  const streamKey =
    manualStreamKey?.flightId === (activeFlightId ?? null)
      ? manualStreamKey.key
      : autoStreamKey;
  const videoError =
    videoErrorStreamKey !== null && videoErrorStreamKey === streamKey
      ? videoErrorMessage
      : null;

  const handleVideoError = useCallback(() => {
    setVideoErrorMessage("Failed to load video stream");
    setVideoErrorStreamKey(streamKey || null);
    setVideoRetryCount((current) => current + 1);
  }, [streamKey]);

  const handleVideoLoad = useCallback(() => {
    setVideoErrorMessage(null);
    setVideoErrorStreamKey(null);
    setVideoRetryCount(0);
  }, []);

  const retryVideo = useCallback(() => {
    setManualStreamKey({ flightId: activeFlightId ?? null, key: Date.now() });
    setVideoErrorMessage(null);
    setVideoErrorStreamKey(null);
  }, [activeFlightId]);

  useEffect(() => disconnect, [disconnect]);

  return {
    ...runtime,
    startingVideo,
    streamKey,
    videoError,
    videoRetryCount,
    handleVideoError,
    handleVideoLoad,
    retryVideo,
  };
}
