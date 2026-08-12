import type { AnalyzeVideoPayload, VideoAsset } from "../types";

export type AnalysisControlsProps = {
  file: File | null;
  video: VideoAsset | null;
  payload: AnalyzeVideoPayload;
  uploading: boolean;
  starting: boolean;
  missionRecordings?: VideoAsset[];
  missionRecordingsLoading?: boolean;
  onSelectMissionRecording?: (recording: VideoAsset) => void;
  onFile: (file: File | null, error: string | null) => void;
  onPayload: (payload: AnalyzeVideoPayload) => void;
  onUpload: () => void;
  onAnalyze: () => void;
};
