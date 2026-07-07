import { useCallback, useEffect, useState } from "react";
import { getToken } from "../../session";
import { useAutoStartVideo } from "../../mission-runtime";

export function useMissionVideoStreamState({
  apiBase,
  activeFlightId,
  droneReady,
  droneConnected,
  onAutoStartVideoError,
}: {
  apiBase: string;
  activeFlightId: string | null;
  droneReady: boolean;
  droneConnected: boolean;
  onAutoStartVideoError: (message: string) => void;
}) {
  const [manualStreamKey, setManualStreamKey] = useState(0);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);
  const videoToken = getToken();

  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase,
    getToken,
    enabled: Boolean(activeFlightId && droneReady),
    onError: onAutoStartVideoError,
    resetKey: activeFlightId ?? "none",
  });

  useEffect(() => {
    if (!droneConnected) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setManualStreamKey(0);
    }
  }, [droneConnected]);

  const handleVideoError = useCallback(() => {
    setVideoError("Failed to load video stream");
    setVideoRetryCount((prev) => prev + 1);
  }, []);

  const handleVideoLoad = useCallback(() => {
    setVideoError(null);
    setVideoRetryCount(0);
  }, []);

  const handleVideoRetry = useCallback(() => {
    setManualStreamKey(Date.now());
    setVideoError(null);
  }, []);

  return {
    streamKey: manualStreamKey || autoStreamKey,
    setStreamKey: setManualStreamKey,
    videoToken,
    startingVideo,
    videoError,
    videoRetryCount,
    handleVideoError,
    handleVideoLoad,
    handleVideoRetry,
  };
}
