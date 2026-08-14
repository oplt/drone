# Video decoder benchmark

Repeatable harness for TASK 3.1. Compares decoder strategies without
changing production code in ``backend/shared/media_frames.py``.

## Runbook

Fixture (machine-readable placeholders):

```sh
python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \
  --fixture --output docs/benchmarks/video-decoder-report.json
python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \
  --render-markdown docs/benchmarks/video-decoder-report.json \
  --markdown-output docs/benchmarks/video-decoder-benchmark.md
```

Live OpenCV modes with synthetic clips when paths are absent:

```sh
python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \
  --synthesize-missing --modes opencv_sequential,opencv_seek \
  --output /tmp/video-decoder-live.json
```

Live against real 1080p/4K assets (set ``path`` in manifest clips):

```sh
python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \
  --manifest backend/scripts/benchmarks/video_decoder_manifest.example.json \
  --output /tmp/video-decoder-live.json \
  --csv-output /tmp/video-decoder-live.csv
```

## Timing methodology

| Metric | Definition |
|--------|------------|
| wall_time_seconds | ``time.monotonic()`` around full decode/sample loop |
| cpu_time_seconds | ``time.process_time()`` delta for benchmark process |
| ram_peak_mb | psutil RSS peak sampled before/after decode |
| timestamp_error_max_seconds | max \|expected − actual\| timestamp on selected frames |
| source_video_minutes_per_wall_minute | processed video minutes / wall-clock minutes |

Modes:

- **opencv_sequential** — decode every frame sequentially; keep sampled indices
- **opencv_seek** — ``CAP_PROP_POS_FRAMES`` seek to sampled indices
- **pyav_sequential** — PyAV sequential decode with stride sampling
- **ffmpeg_pipe** — ``ffmpeg`` ``fps`` filter to rawvideo pipe

- Report mode: `fixture`
- Manifest: `video-decoder-representative`

## Results

| clip | sample FPS | mode | wall s | CPU s | decoded | selected | RAM MiB | ts err s | vid min / wall min |
|------|----------:|------|-------:|------:|--------:|---------:|--------:|---------:|-------------------:|
| 1080p_h264_short | 0.5 | opencv_sequential | 32.40 | 32.40 | 900 | 15 | 380 | 0.0000 | 0.93 |
| 1080p_h264_short | 0.5 | opencv_seek | 0.78 | 0.39 | 15 | 15 | 380 | 0.0400 | 38.71 |
| 1080p_h264_short | 0.5 | pyav_sequential | 1.32 | 1.17 | 900 | 15 | 380 | 0.0100 | 22.64 |
| 1080p_h264_short | 0.5 | ffmpeg_pipe | 0.50 | 0.21 | 15 | 15 | 380 | 0.0000 | 60.00 |
| 1080p_h264_short | 1.0 | opencv_sequential | 16.20 | 16.20 | 900 | 30 | 380 | 0.0000 | 1.85 |
| 1080p_h264_short | 1.0 | opencv_seek | 1.02 | 0.51 | 30 | 30 | 380 | 0.0400 | 29.27 |
| 1080p_h264_short | 1.0 | pyav_sequential | 1.38 | 1.21 | 900 | 30 | 380 | 0.0100 | 21.82 |
| 1080p_h264_short | 1.0 | ffmpeg_pipe | 0.62 | 0.26 | 30 | 30 | 380 | 0.0000 | 48.00 |
| 1080p_h264_short | 2.0 | opencv_sequential | 8.10 | 8.10 | 900 | 60 | 380 | 0.0000 | 3.70 |
| 1080p_h264_short | 2.0 | opencv_seek | 1.52 | 0.76 | 60 | 60 | 380 | 0.0400 | 19.67 |
| 1080p_h264_short | 2.0 | pyav_sequential | 1.48 | 1.30 | 900 | 60 | 380 | 0.0100 | 20.34 |
| 1080p_h264_short | 2.0 | ffmpeg_pipe | 0.88 | 0.37 | 60 | 60 | 380 | 0.0000 | 34.29 |
| 1080p_h264_short | 5.0 | opencv_sequential | 5.40 | 5.40 | 900 | 150 | 380 | 0.0000 | 5.56 |
| 1080p_h264_short | 5.0 | opencv_seek | 2.02 | 1.01 | 150 | 150 | 380 | 0.0400 | 14.81 |
| 1080p_h264_short | 5.0 | pyav_sequential | 1.57 | 1.39 | 900 | 150 | 380 | 0.0100 | 19.05 |
| 1080p_h264_short | 5.0 | ffmpeg_pipe | 1.12 | 0.47 | 150 | 150 | 380 | 0.0000 | 26.67 |
| 1080p_h264_long | 0.5 | opencv_sequential | 648.00 | 648.00 | 18000 | 300 | 380 | 0.0000 | 0.93 |
| 1080p_h264_long | 0.5 | opencv_seek | 15.50 | 7.75 | 300 | 300 | 380 | 0.0400 | 38.71 |
| 1080p_h264_long | 0.5 | pyav_sequential | 26.50 | 23.32 | 18000 | 300 | 380 | 0.0100 | 22.64 |
| 1080p_h264_long | 0.5 | ffmpeg_pipe | 10.00 | 4.20 | 300 | 300 | 380 | 0.0000 | 60.00 |
| 1080p_h264_long | 1.0 | opencv_sequential | 324.00 | 324.00 | 18000 | 600 | 380 | 0.0000 | 1.85 |
| 1080p_h264_long | 1.0 | opencv_seek | 20.50 | 10.25 | 600 | 600 | 380 | 0.0400 | 29.27 |
| 1080p_h264_long | 1.0 | pyav_sequential | 27.50 | 24.20 | 18000 | 600 | 380 | 0.0100 | 21.82 |
| 1080p_h264_long | 1.0 | ffmpeg_pipe | 12.50 | 5.25 | 600 | 600 | 380 | 0.0000 | 48.00 |
| 1080p_h264_long | 2.0 | opencv_sequential | 162.00 | 162.00 | 18000 | 1200 | 380 | 0.0000 | 3.70 |
| 1080p_h264_long | 2.0 | opencv_seek | 30.50 | 15.25 | 1200 | 1200 | 380 | 0.0400 | 19.67 |
| 1080p_h264_long | 2.0 | pyav_sequential | 29.50 | 25.96 | 18000 | 1200 | 380 | 0.0100 | 20.34 |
| 1080p_h264_long | 2.0 | ffmpeg_pipe | 17.50 | 7.35 | 1200 | 1200 | 380 | 0.0000 | 34.29 |
| 1080p_h264_long | 5.0 | opencv_sequential | 108.00 | 108.00 | 18000 | 3000 | 380 | 0.0000 | 5.56 |
| 1080p_h264_long | 5.0 | opencv_seek | 40.50 | 20.25 | 3000 | 3000 | 380 | 0.0400 | 14.81 |
| 1080p_h264_long | 5.0 | pyav_sequential | 31.50 | 27.72 | 18000 | 3000 | 380 | 0.0100 | 19.05 |
| 1080p_h264_long | 5.0 | ffmpeg_pipe | 22.50 | 9.45 | 3000 | 3000 | 380 | 0.0000 | 26.67 |
| 4k_h264_short | 0.5 | opencv_sequential | 106.92 | 106.92 | 1350 | 23 | 1180 | 0.0000 | 0.42 |
| 4k_h264_short | 0.5 | opencv_seek | 2.56 | 1.28 | 23 | 23 | 1180 | 0.0400 | 17.60 |
| 4k_h264_short | 0.5 | pyav_sequential | 4.37 | 3.85 | 1350 | 23 | 1180 | 0.0100 | 10.29 |
| 4k_h264_short | 0.5 | ffmpeg_pipe | 1.65 | 0.69 | 23 | 23 | 1180 | 0.0000 | 27.27 |
| 4k_h264_short | 1.0 | opencv_sequential | 53.46 | 53.46 | 1350 | 45 | 1180 | 0.0000 | 0.84 |
| 4k_h264_short | 1.0 | opencv_seek | 3.38 | 1.69 | 45 | 45 | 1180 | 0.0400 | 13.30 |
| 4k_h264_short | 1.0 | pyav_sequential | 4.54 | 3.99 | 1350 | 45 | 1180 | 0.0100 | 9.92 |
| 4k_h264_short | 1.0 | ffmpeg_pipe | 2.06 | 0.87 | 45 | 45 | 1180 | 0.0000 | 21.82 |
| 4k_h264_short | 2.0 | opencv_sequential | 26.73 | 26.73 | 1350 | 90 | 1180 | 0.0000 | 1.68 |
| 4k_h264_short | 2.0 | opencv_seek | 5.03 | 2.52 | 90 | 90 | 1180 | 0.0400 | 8.94 |
| 4k_h264_short | 2.0 | pyav_sequential | 4.87 | 4.28 | 1350 | 90 | 1180 | 0.0100 | 9.25 |
| 4k_h264_short | 2.0 | ffmpeg_pipe | 2.89 | 1.21 | 90 | 90 | 1180 | 0.0000 | 15.59 |
| 4k_h264_short | 5.0 | opencv_sequential | 17.82 | 17.82 | 1350 | 225 | 1180 | 0.0000 | 2.52 |
| 4k_h264_short | 5.0 | opencv_seek | 6.68 | 3.34 | 225 | 225 | 1180 | 0.0400 | 6.73 |
| 4k_h264_short | 5.0 | pyav_sequential | 5.20 | 4.57 | 1350 | 225 | 1180 | 0.0100 | 8.66 |
| 4k_h264_short | 5.0 | ffmpeg_pipe | 3.71 | 1.56 | 225 | 225 | 1180 | 0.0000 | 12.12 |
| 4k_h265_short | 0.5 | opencv_sequential | 122.96 | 122.96 | 1350 | 23 | 1180 | 0.0000 | 0.37 |
| 4k_h265_short | 0.5 | opencv_seek | 2.94 | 1.47 | 23 | 23 | 1180 | 0.0400 | 15.30 |
| 4k_h265_short | 0.5 | pyav_sequential | 5.03 | 4.42 | 1350 | 23 | 1180 | 0.0100 | 8.95 |
| 4k_h265_short | 0.5 | ffmpeg_pipe | 1.90 | 0.80 | 23 | 23 | 1180 | 0.0000 | 23.72 |
| 4k_h265_short | 1.0 | opencv_sequential | 61.48 | 61.48 | 1350 | 45 | 1180 | 0.0000 | 0.73 |
| 4k_h265_short | 1.0 | opencv_seek | 3.89 | 1.95 | 45 | 45 | 1180 | 0.0400 | 11.57 |
| 4k_h265_short | 1.0 | pyav_sequential | 5.22 | 4.59 | 1350 | 45 | 1180 | 0.0100 | 8.62 |
| 4k_h265_short | 1.0 | ffmpeg_pipe | 2.37 | 1.00 | 45 | 45 | 1180 | 0.0000 | 18.97 |
| 4k_h265_short | 2.0 | opencv_sequential | 30.74 | 30.74 | 1350 | 90 | 1180 | 0.0000 | 1.46 |
| 4k_h265_short | 2.0 | opencv_seek | 5.79 | 2.89 | 90 | 90 | 1180 | 0.0400 | 7.78 |
| 4k_h265_short | 2.0 | pyav_sequential | 5.60 | 4.93 | 1350 | 90 | 1180 | 0.0100 | 8.04 |
| 4k_h265_short | 2.0 | ffmpeg_pipe | 3.32 | 1.40 | 90 | 90 | 1180 | 0.0000 | 13.55 |
| 4k_h265_short | 5.0 | opencv_sequential | 20.49 | 20.49 | 1350 | 225 | 1180 | 0.0000 | 2.20 |
| 4k_h265_short | 5.0 | opencv_seek | 7.68 | 3.84 | 225 | 225 | 1180 | 0.0400 | 5.86 |
| 4k_h265_short | 5.0 | pyav_sequential | 5.98 | 5.26 | 1350 | 225 | 1180 | 0.0100 | 7.53 |
| 4k_h265_short | 5.0 | ffmpeg_pipe | 4.27 | 1.79 | 225 | 225 | 1180 | 0.0000 | 10.54 |

> Fixture timings are synthetic placeholders. Replace by running live
> commands against representative 1080p/4K H.264/H.265 clips.

## Adoption analysis (TASK 3.2)

- Baseline mode: `opencv_sequential`
- CPU threshold: `30.0%`
- Wall-time threshold: `25.0%`
- Qualifying cases: `48`
- Recommend default change: **no**
- Suggested opt-in decoder: `ffmpeg_pipe`
- Notes: Fixture/live report shows threshold wins, but production default stays opencv_sequential until representative hardware validation is recorded.

