from __future__ import annotations

from datetime import datetime

from scipy.optimize import linear_sum_assignment

from backend.modules.patrol.vision.models import Detection, Track


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
    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_missed_frames: int = 20,
        max_center_distance_px: float = 180.0,
        confidence_smoothing_alpha: float = 0.35,
    ):
        self.iou_threshold = float(iou_threshold)
        self.max_missed_frames = int(max_missed_frames)
        self.max_center_distance_px = max(1.0, float(max_center_distance_px))
        self.confidence_smoothing_alpha = max(0.01, min(1.0, float(confidence_smoothing_alpha)))
        self.next_id = 1
        self.tracks: dict[int, Track] = {}
        self.missed: dict[int, int] = {}

    def update(self, detections: list[Detection], now: datetime) -> list[Track]:
        updated_ids: set[int] = set()

        assigned_tracks: set[int] = set()
        assigned_detections: set[int] = set()
        # Spatial gating removes impossible pairs before Hungarian assignment.
        # Cost ties are deterministic because track and detection order is stable.
        labels = sorted(
            {track.label for track in self.tracks.values()}
            | {det.label for det in detections}
        )
        for label in labels:
            track_ids = [
                track_id for track_id, track in self.tracks.items() if track.label == label
            ]
            detection_indexes = [
                index for index, det in enumerate(detections) if det.label == label
            ]
            if not track_ids or not detection_indexes:
                continue
            costs: list[list[float]] = []
            for track_id in track_ids:
                track = self.tracks[track_id]
                row: list[float] = []
                for det_index in detection_indexes:
                    det = detections[det_index]
                    det_center = _centroid(det.bbox)
                    distance = (
                        (track.centroid[0] - det_center[0]) ** 2
                        + (track.centroid[1] - det_center[1]) ** 2
                    ) ** 0.5
                    score = _iou(track.bbox, det.bbox)
                    row.append(
                        1.0 - score
                        if distance <= self.max_center_distance_px and score >= self.iou_threshold
                        else 1_000_000.0
                    )
                costs.append(row)
            matched_rows, matched_columns = linear_sum_assignment(costs)
            assignments = sorted(
                (
                    costs[row][column],
                    track_ids[row],
                    detection_indexes[column],
                )
                for row, column in zip(matched_rows, matched_columns, strict=True)
                if costs[row][column] < 1_000_000.0
            )
            for _cost, track_id, det_index in assignments:
                if track_id in assigned_tracks or det_index in assigned_detections:
                    continue
                det = detections[det_index]
                track = self.tracks[track_id]
                previous_confidence = float(track.meta.get("confidence_ema", track.confidence))
                confidence = (
                    self.confidence_smoothing_alpha * det.confidence
                    + (1.0 - self.confidence_smoothing_alpha) * previous_confidence
                )
                track.bbox = det.bbox
                track.centroid = _centroid(det.bbox)
                track.confidence = confidence
                track.meta["confidence_ema"] = confidence
                track.meta["stability_frames"] = int(track.meta.get("stability_frames", 0)) + 1
                track.last_seen = now
                track.age_frames += 1
                updated_ids.add(track_id)
                assigned_tracks.add(track_id)
                assigned_detections.add(det_index)
                self.missed[track_id] = 0

        for det_index, det in enumerate(detections):
            if det_index in assigned_detections:
                continue
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
                meta={"confidence_ema": det.confidence, "stability_frames": 1},
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
