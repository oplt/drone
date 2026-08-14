import { useCallback, useState } from "react";
import { useAutoStartVideo } from "../../mission-runtime";
import { getToken } from "../../session";

type UseAnimalFarmVideoSessionOptions = {
  apiBase: string;
  activeFlightId: string | null;
  droneConnected: boolean;
  addError: (message: string) => void;
};

export function useAnimalFarmVideoSession({
  apiBase,
  activeFlightId,
  droneConnected,
  addError,
}: UseAnimalFarmVideoSessionOptions) {
  const [manualStreamKey, setManualStreamKey] = useState(0);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);

  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase,
    getToken,
    enabled: Boolean(activeFlightId && droneConnected),
    onError: addError,
    resetKey: activeFlightId ?? "none",
  });

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

  const streamKey = droneConnected ? manualStreamKey || autoStreamKey : 0;

  return {
    streamKey,
    startingVideo,
    videoError,
    videoRetryCount,
    handleVideoError,
    handleVideoLoad,
    handleVideoRetry,
  };
}
