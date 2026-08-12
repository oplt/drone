from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.modules.video_analysis.service.frame_extractor import (
    iter_frames,
    read_video_metadata,
)

MIN_WIDTH = 320
MIN_HEIGHT = 240
MIN_BLUR_VARIANCE = 20.0
MIN_EXPOSURE = 8.0
MAX_EXPOSURE = 247.0
MAX_HASH_DISTANCE = 6


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


@dataclass(frozen=True)
class CurationResult:
    candidate_frames: int
    rejected_quality: int
    rejected_duplicates: int
    selected: list[CuratedFrame]
    rejected: list[dict]
    effective_interval_seconds: float

    def manifest(self) -> dict:
        return {
            "candidate_frames": self.candidate_frames,
            "rejected_quality": self.rejected_quality,
            "rejected_duplicates": self.rejected_duplicates,
            "selected_frames": len(self.selected),
            "effective_interval_seconds": self.effective_interval_seconds,
            "selected": [
                {**asdict(frame), "quality": asdict(frame.quality)} for frame in self.selected
            ],
            "rejected": self.rejected,
        }


def average_hash(gray: np.ndarray) -> str:
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    bits = small >= float(small.mean())
    return f"{int(''.join('1' if value else '0' for value in bits.flatten()), 2):016x}"


def hash_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


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
    selected: list[CuratedFrame] = []
    rejected: list[dict] = []
    accepted_hashes: list[str] = []
    candidates = quality_rejected = duplicate_rejected = 0

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
        if any(
            hash_distance(perceptual_hash, previous) <= MAX_HASH_DISTANCE
            for previous in accepted_hashes
        ):
            duplicate_rejected += 1
            rejected.append({**base, "reason": "near_duplicate"})
            continue

        target = output / f"frame-{frame.frame_index:08d}.jpg"
        ok, encoded = cv2.imencode(".jpg", frame.image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            quality_rejected += 1
            rejected.append({**base, "reason": "encode_failed"})
            continue
        target.write_bytes(encoded.tobytes())
        accepted_hashes.append(perceptual_hash)
        height, width = frame.image_bgr.shape[:2]
        selected.append(
            CuratedFrame(
                frame_index=frame.frame_index,
                timestamp_seconds=frame.timestamp_seconds,
                path=str(target),
                width=width,
                height=height,
                perceptual_hash=perceptual_hash,
                quality=quality,
            )
        )

    return CurationResult(
        candidate_frames=candidates,
        rejected_quality=quality_rejected,
        rejected_duplicates=duplicate_rejected,
        selected=selected,
        rejected=rejected,
        effective_interval_seconds=effective_interval,
    )
