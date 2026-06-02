import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { liveObjectDetectionKeys } from "../../../app/config/queryKeys";
import {
  getLiveObjectDetectionStatus,
  startLiveObjectDetection,
  stopLiveObjectDetection,
} from "../api/liveObjectDetectionApi";

export function useLiveObjectDetection() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: liveObjectDetectionKeys.status(),
    queryFn: getLiveObjectDetectionStatus,
    refetchInterval: (query) => (query.state.data?.running ? 1000 : 5000),
    staleTime: 2000,
  });
  const toggle = useMutation({
    mutationFn: () =>
      status.data?.running ? stopLiveObjectDetection() : startLiveObjectDetection(),
    onSuccess: (next) =>
      queryClient.setQueryData(liveObjectDetectionKeys.status(), next),
  });

  return {
    enabled: Boolean(status.data?.running),
    status: status.data,
    detections: status.data?.detections ?? [],
    error: toggle.error?.message ?? status.data?.last_error ?? null,
    toggling: toggle.isPending,
    toggle: () => toggle.mutate(),
  };
}
