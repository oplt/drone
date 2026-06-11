import { httpRequest } from "../../../shared/api/httpClient";

export type VideoStreamStatus = {
  state?: "ready" | "warming" | "unavailable" | "idle";
  first_frame_available?: boolean;
  camera_stream_topic_found?: boolean;
  gazebo_streaming_enabled?: boolean;
  udp_first_frame_received?: boolean;
  last_error?: string | null;
  retry_after_ms?: number;
  failure_count?: number;
  source?: string;
  started?: boolean;
  healthy?: boolean;
};

export async function fetchVideoStatus(
  token?: string | null,
): Promise<VideoStreamStatus> {
  return httpRequest<VideoStreamStatus>("/video/status", {
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function startVideoStream(token?: string | null): Promise<void> {
  await httpRequest<void>("/video/start", {
    method: "POST",
    token,
    skipUnauthorizedRedirect: true,
  });
}
