import { httpRequest } from "../../../shared/api/httpClient";

export type LiveFrameDetection = {
  label: string;
  confidence: number;
  bbox: [number, number, number, number];
  image_width: number;
  image_height: number;
};

export type LiveObjectDetectionStatus = {
  running: boolean;
  last_error?: string | null;
  frames_processed: number;
  detections: LiveFrameDetection[];
  config?: {
    detector_model_path?: string;
    target_fps?: number;
  };
};

export async function getLiveObjectDetectionStatus(): Promise<LiveObjectDetectionStatus> {
  return httpRequest<LiveObjectDetectionStatus>("/api/ml/status");
}

export async function startLiveObjectDetection(): Promise<LiveObjectDetectionStatus> {
  return httpRequest<LiveObjectDetectionStatus>("/api/ml/start", {
    method: "POST",
    body: {},
  });
}

export async function stopLiveObjectDetection(): Promise<LiveObjectDetectionStatus> {
  return httpRequest<LiveObjectDetectionStatus>("/api/ml/stop", { method: "POST" });
}
