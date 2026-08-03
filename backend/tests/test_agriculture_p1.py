from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np

from backend.modules.agriculture.aggregation import aggregate_detections
from backend.modules.agriculture.heuristics import anomaly_signature, infer_row_structure, segment_rgb_crop_soil_water
from backend.modules.agriculture.quality import aggregate_quality, compute_frame_quality
from backend.modules.agriculture.live import LiveAdvisory, LiveAgricultureProcessor, LiveFrame
from backend.modules.agriculture.stand import summarize_stands


def test_quality_gate_metrics_and_summary_are_deterministic():
    image = np.zeros((80, 120, 3), dtype=np.uint8)
    image[:, 20:100] = (30, 150, 30)
    first = compute_frame_quality(image)
    second = compute_frame_quality(image, previous_bgr=image)
    assert first.metrics == compute_frame_quality(image).metrics
    assert second.metrics["duplicate_score"] > 0.98
    summary = aggregate_quality([first, second])
    assert summary["frame_count"] == 2
    assert "score" in summary


def test_detection_aggregation_deduplicates_frames_and_preserves_unresolved():
    rows = [
        SimpleNamespace(id="a", label="weed", confidence=0.8, lat=50.0, lon=4.0, timestamp_seconds=1.0),
        SimpleNamespace(id="b", label="weed", confidence=0.9, lat=50.00001, lon=4.00001, timestamp_seconds=2.0),
        SimpleNamespace(id="c", label="water", confidence=0.7, lat=None, lon=None, timestamp_seconds=3.0),
    ]
    output = aggregate_detections(rows, cluster_radius_m=8)
    assert len(output) == 2
    weed = next(item for item in output if item["observation_type"] == "weed")
    assert len(weed["evidence_ids"]) == 2
    assert weed["georef_status"] == "resolved"
    assert next(item for item in output if item["observation_type"] == "standing_water")["georef_status"] == "unresolved"


def test_rgb_fallback_exposes_canopy_soil_water_and_row_confidence():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[:, :50] = (20, 140, 20)
    segmentation = segment_rgb_crop_soil_water(image)
    assert segmentation["canopy_pct"] > 40
    rows = infer_row_structure(segmentation["masks"]["crop"])
    assert "confidence" in rows
    assert anomaly_signature(current={"canopy": 0.4}, baseline=None)["status"] == "cold_start"


def test_live_processor_is_bounded_and_expires_stale_results():
    processor = LiveAgricultureProcessor(max_queue=1, stale_after_s=2)
    assert processor.submit(LiveFrame(1, 1, "frame-1", 0.0)) is True
    assert processor.submit(LiveFrame(2, 2, "frame-2", 1.0)) is False
    result = processor.process_one(lambda image: LiveAdvisory(2, 2, "pass", (), None, 9.0), now=4.0)
    assert result is not None and result.state == "stale"


def test_stand_summary_uses_row_segments_not_raw_frame_count():
    rows = [SimpleNamespace(lat=50.0, lon=4.0), SimpleNamespace(lat=50.00001, lon=4.00001), SimpleNamespace(lat=50.00002, lon=4.00002)]
    summary = summarize_stands(rows, row_spacing_m=3, row_direction_deg=0)
    assert summary["estimated_count"] == 3
    assert "gap_segment_count" in summary and "double_cluster_count" in summary
