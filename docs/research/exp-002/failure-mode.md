# EXP-002 failure mode — stand count stability

## Named product failure

Farmers using **stand_count** need stable plant counts across short repeat
clips. Enabling SAHI + tracking by default may improve small-object recall but
can inflate counts via fragmentation / ID switches without audited evidence.

## Outcome metric

Primary: **relative count error** `|pred_count − gt_count| / gt_count`

Secondary:

- Small-box recall @ IoU 0.5 (boxes with area ≤ 32² px)
- Track fragmentation proxy: unique track ids / GT count (when tracking on)
- Stage latency budget (relative to standard profile)
- Peak memory / cost proxy (detection count × latency)

## Pre-registered gates (from release_governance + PERF)

| Gate | Threshold |
|---|---|
| count_error | ≤ 0.15 |
| small_object_recall | ≥ baseline_standard − 0.05 **and** ≥ 0.60 |
| fragmentation_ratio | ≤ 1.35 when tracking enabled |
| latency_vs_standard | ≤ 2.5× wall for SAHI profiles |
| memory/cost | ≤ 2.0× detection-work units vs standard |

Promotion requires **all** gates vs the standard (no-SAHI, no-track) baseline on
the fixed fixture pack, plus locked model checksum. Generic FPS gains are
insufficient.

## Non-goals

- Exposing SAHI/YOLO brand toggles in farmer agriculture UX
- Promoting alternate trackers without fixtures (ByteTrack only today)
- Changing Vision map50 release policy alone as proxy for this study
