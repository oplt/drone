from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.shared.media_frames import (
    iter_frames,
    read_video_metadata,
)

MIN_WIDTH = 320
MIN_HEIGHT = 240
MIN_BLUR_VARIANCE = 20.0
MIN_EXPOSURE = 8.0
MAX_EXPOSURE = 247.0
MAX_HASH_DISTANCE = 6
TEMPORAL_HASH_WINDOW = 16
HASH_BUCKET_LIMIT = 64
HASH_PREFIX_LENGTH = 3


@dataclass(frozen=True)
class FrameQuality:
    blur_variance: float
    mean_exposure: float
    score: float
    rejection_reasons: list[str]


@dataclass(frozen=True)
class CuratedFrame:
    frame_index: int
    timestamp_seconds: float
    path: str
    width: int
    height: int
    perceptual_hash: str
    quality: FrameQuality
    selected: bool = True
    duplicate_cluster_id: str | None = None


@dataclass(frozen=True)
class CurationResult:
    candidate_frames: int
    rejected_quality: int
    rejected_duplicates: int
    frames: list[CuratedFrame]
    rejected: list[dict]
    effective_interval_seconds: float
    comparison_count: int = 0
    duplicate_cluster_count: int = 0

    @property
    def selected(self) -> list[CuratedFrame]:
        return [frame for frame in self.frames if frame.selected]

    def manifest(self) -> dict:
        return {
            "candidate_frames": self.candidate_frames,
            "rejected_quality": self.rejected_quality,
            "rejected_duplicates": self.rejected_duplicates,
            "selected_frames": len(self.selected),
            "duplicate_cluster_count": self.duplicate_cluster_count,
            "comparison_count": self.comparison_count,
            "effective_interval_seconds": self.effective_interval_seconds,
            "frames": [
                {**asdict(frame), "quality": asdict(frame.quality)} for frame in self.frames
            ],
            "rejected": self.rejected,
        }


def average_hash(gray: np.ndarray) -> str:
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    bits = small >= float(small.mean())
    return f"{int(''.join('1' if value else '0' for value in bits.flatten()), 2):016x}"


def hash_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def prefix_probe_keys(
    perceptual_hash: str,
    *,
    prefix_len: int = HASH_PREFIX_LENGTH,
    max_bit_dist: int = MAX_HASH_DISTANCE,
) -> list[str]:
    """Return the exact hash prefix followed by nearby prefixes in Hamming space."""
    prefix = perceptual_hash[:prefix_len].lower()
    query = int(prefix, 16)
    bit_count = prefix_len * 4
    keys = [prefix]
    keys.extend(
        f"{candidate:0{prefix_len}x}"
        for candidate in range(1 << bit_count)
        if candidate != query and (candidate ^ query).bit_count() <= max_bit_dist
    )
    return keys


def assess_quality(image_bgr: np.ndarray) -> FrameQuality:
    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    exposure = float(gray.mean())
    reasons: list[str] = []
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        reasons.append("resolution_too_small")
    if blur < MIN_BLUR_VARIANCE:
        reasons.append("too_blurry")
    if exposure < MIN_EXPOSURE:
        reasons.append("too_dark")
    elif exposure > MAX_EXPOSURE:
        reasons.append("too_bright")
    blur_score = min(1.0, blur / 200.0)
    exposure_score = max(0.0, 1.0 - abs(exposure - 127.5) / 127.5)
    resolution_score = min(1.0, (width * height) / (640 * 480))
    score = round(0.45 * blur_score + 0.35 * exposure_score + 0.2 * resolution_score, 4)
    return FrameQuality(blur, exposure, score, reasons)


def curate_video_frames(
    video_path: str | Path,
    output_dir: str | Path,
    *,
    interval_seconds: float,
    max_frames: int,
) -> CurationResult:
    metadata = read_video_metadata(video_path)
    uniform_interval = metadata.duration_seconds / max_frames if max_frames else interval_seconds
    effective_interval = max(interval_seconds, uniform_interval)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frames: list[CuratedFrame] = []
    rejected: list[dict] = []
    recent: deque[tuple[int, str]] = deque(maxlen=TEMPORAL_HASH_WINDOW)
    buckets: dict[str, deque[tuple[int, str]]] = defaultdict(
        lambda: deque(maxlen=HASH_BUCKET_LIMIT)
    )
    candidates = quality_rejected = duplicate_rejected = 0
    comparison_count = 0
    duplicate_clusters: set[str] = set()

    for frame in iter_frames(video_path, every_seconds=effective_interval):
        if candidates >= max_frames:
            break
        candidates += 1
        quality = assess_quality(frame.image_bgr)
        gray = cv2.cvtColor(frame.image_bgr, cv2.COLOR_BGR2GRAY)
        perceptual_hash = average_hash(gray)
        base = {
            "frame_index": frame.frame_index,
            "timestamp_seconds": frame.timestamp_seconds,
            "quality": asdict(quality),
            "perceptual_hash": perceptual_hash,
        }
        if quality.rejection_reasons:
            quality_rejected += 1
            rejected.append({**base, "reason": "quality"})
            continue
        comparison_candidates = {item[0]: item[1] for item in recent}
        for key in prefix_probe_keys(perceptual_hash):
            for item in buckets[key]:
                if item[0] not in comparison_candidates:
                    comparison_candidates[item[0]] = item[1]
                if len(comparison_candidates) >= TEMPORAL_HASH_WINDOW + HASH_BUCKET_LIMIT:
                    break
            if len(comparison_candidates) >= TEMPORAL_HASH_WINDOW + HASH_BUCKET_LIMIT:
                break
        duplicate_of: int | None = None
        for previous_index, previous_hash in comparison_candidates.items():
            comparison_count += 1
            if hash_distance(perceptual_hash, previous_hash) <= MAX_HASH_DISTANCE:
                duplicate_of = previous_index
                break
        duplicate_cluster_id = (
            f"near-duplicate:{duplicate_of}" if duplicate_of is not None else None
        )
        if duplicate_cluster_id is not None:
            duplicate_rejected += 1
            duplicate_clusters.add(duplicate_cluster_id)
            rejected.append(
                {
                    **base,
                    "reason": "near_duplicate",
                    "duplicate_cluster_id": duplicate_cluster_id,
                }
            )

        target = output / f"frame-{frame.frame_index:08d}.jpg"
        ok, encoded = cv2.imencode(".jpg", frame.image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            quality_rejected += 1
            rejected.append({**base, "reason": "encode_failed"})
            continue
        target.write_bytes(encoded.tobytes())
        height, width = frame.image_bgr.shape[:2]
        frames.append(
            CuratedFrame(
                frame_index=frame.frame_index,
                timestamp_seconds=frame.timestamp_seconds,
                path=str(target),
                width=width,
                height=height,
                perceptual_hash=perceptual_hash,
                quality=quality,
                selected=duplicate_cluster_id is None,
                duplicate_cluster_id=duplicate_cluster_id,
            )
        )
        if duplicate_cluster_id is None:
            accepted = (frame.frame_index, perceptual_hash)
            recent.append(accepted)
            buckets[perceptual_hash[:HASH_PREFIX_LENGTH]].append(accepted)

    return CurationResult(
        candidate_frames=candidates,
        rejected_quality=quality_rejected,
        rejected_duplicates=duplicate_rejected,
        frames=frames,
        rejected=rejected,
        effective_interval_seconds=effective_interval,
        comparison_count=comparison_count,
        duplicate_cluster_count=len(duplicate_clusters),
    )
