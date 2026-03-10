from __future__ import annotations

from datetime import datetime
from typing import List

from backend.ml.patrol.models import Detection, Track


def _centroid(bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class SimpleTracker:
    def __init__(self, iou_threshold: float = 0.3, max_missed_frames: int = 20):
        self.iou_threshold = float(iou_threshold)
        self.max_missed_frames = int(max_missed_frames)
        self.next_id = 1
        self.tracks: dict[int, Track] = {}
        self.missed: dict[int, int] = {}

    def update(self, detections: List[Detection], now: datetime) -> List[Track]:
        updated_ids: set[int] = set()

        for det in detections:
            best_id = None
            best_score = 0.0
            for track_id, track in self.tracks.items():
                if track.label != det.label:
                    continue
                score = _iou(track.bbox, det.bbox)
                if score > best_score:
                    best_score = score
                    best_id = track_id

            if best_id is not None and best_score >= self.iou_threshold:
                track = self.tracks[best_id]
                track.bbox = det.bbox
                track.centroid = _centroid(det.bbox)
                track.confidence = det.confidence
                track.last_seen = now
                track.age_frames += 1
                updated_ids.add(best_id)
                self.missed[best_id] = 0
            else:
                track_id = self.next_id
                self.next_id += 1
                self.tracks[track_id] = Track(
                    track_id=track_id,
                    label=det.label,
                    confidence=det.confidence,
                    bbox=det.bbox,
                    centroid=_centroid(det.bbox),
                    age_frames=1,
                    first_seen=now,
                    last_seen=now,
                    meta={},
                )
                updated_ids.add(track_id)
                self.missed[track_id] = 0

        stale: list[int] = []
        for track_id in list(self.tracks.keys()):
            if track_id not in updated_ids:
                self.missed[track_id] = self.missed.get(track_id, 0) + 1
                if self.missed[track_id] > self.max_missed_frames:
                    stale.append(track_id)

        for track_id in stale:
            self.tracks.pop(track_id, None)
            self.missed.pop(track_id, None)

        return list(self.tracks.values())
