import { useMissionVideo } from "./useMissionVideo";

/** @deprecated Prefer useMissionVideo from mission-runtime. */
export function useAutoStartVideo({
  enabled,
  onError,
  resetKey,
  apiBase: _apiBase,
  getToken: _getToken,
}: {
  apiBase?: string;
  getToken?: () => string | null;
  enabled: boolean;
  onError: (msg: string) => void;
  resetKey?: string;
}) {
  return useMissionVideo({
    enabled,
    onError,
    resetKey,
  });
}
