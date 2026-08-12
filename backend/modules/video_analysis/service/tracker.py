from __future__ import annotations

from dataclasses import replace

import numpy as np
import supervision as sv

from backend.modules.video_analysis.service.detector import FrameDetection


class FrameTracker:
    """Class-aware ByteTrack adapter with globally unique IDs for one analysis job."""

    def __init__(self, *, sampled_frame_rate: float) -> None:
        self.sampled_frame_rate = max(0.1, sampled_frame_rate)
        self.trackers: dict[str, object] = {}
        self.global_ids: dict[tuple[str, int], int] = {}
        self.next_global_id = 1

    def _tracker(self, label: str):
        tracker = self.trackers.get(label)
        if tracker is None:
            tracker = sv.ByteTrack(
                track_activation_threshold=0.2,
                lost_track_buffer=15,
                minimum_matching_threshold=0.8,
                frame_rate=self.sampled_frame_rate,
                minimum_consecutive_frames=1,
            )
            self.trackers[label] = tracker
        return tracker

    def update(self, detections: list[FrameDetection]) -> list[FrameDetection]:
        output = list(detections)
        labels = set(self.trackers) | {item.label for item in detections}
        for label in labels:
            indices = [index for index, item in enumerate(detections) if item.label == label]
            if indices:
                supervision_detections = sv.Detections(
                    xyxy=np.asarray(
                        [
                            [
                                detections[index].x1,
                                detections[index].y1,
                                detections[index].x2,
                                detections[index].y2,
                            ]
                            for index in indices
                        ],
                        dtype=np.float32,
                    ),
                    confidence=np.asarray(
                        [detections[index].confidence for index in indices], dtype=np.float32
                    ),
                    data={"source_index": np.asarray(indices, dtype=np.int64)},
                )
            else:
                supervision_detections = sv.Detections.empty()
                supervision_detections.confidence = np.asarray([], dtype=np.float32)
                supervision_detections.data["source_index"] = np.asarray([], dtype=np.int64)
            tracked = self._tracker(label).update_with_detections(supervision_detections)
            tracker_ids = tracked.tracker_id
            source_indices = tracked.data.get("source_index", [])
            if tracker_ids is None:
                continue
            for source_index, local_id in zip(source_indices, tracker_ids, strict=False):
                key = (label, int(local_id))
                global_id = self.global_ids.get(key)
                if global_id is None:
                    global_id = self.next_global_id
                    self.global_ids[key] = global_id
                    self.next_global_id += 1
                index = int(source_index)
                output[index] = replace(output[index], track_id=global_id)
        return output
