# Video inference batch-size benchmark

Repeatable harness for TASK 3.4. Compares standard Ultralytics YOLO
``predict_batch`` throughput by device class and inference profile.

## Runbook

Fixture (no GPU):

```sh
python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \
  --fixture --output docs/benchmarks/video-inference-batch-report.json
python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \
  --render-markdown docs/benchmarks/video-inference-batch-report.json \
  --markdown-output docs/benchmarks/video-inference-batch-benchmark.md
```

Live (torch + ultralytics + optional NVIDIA GPU):

```sh
python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \
  --output /tmp/video-inference-batch-report.json
```

## Timing methodology

| Metric | Definition |
|--------|------------|
| images_per_second | total images / wall seconds in timed loop |
| batch_latency_ms | mean wall time per ``predict()`` batch |
| per_image_latency_ms | batch latency / batch size |
| gpu_util_avg_pct | ``nvidia-smi`` GPU utilization sampled every 0.5s |
| vram_peak_mb | peak VRAM from ``nvidia-smi`` and ``torch.cuda.max_memory_allocated`` |

- Report mode: `fixture`
- Manifest: `video-inference-batch-representative`
- Model: `yolo26n.pt`

## Results

| device | profile | batch | img/s | batch ms | img ms | GPU % | VRAM MiB | stable | OOM |
|--------|---------|------:|------:|---------:|-------:|------:|---------:|:------:|:---:|
| cuda | standard_1080p | 1 | 14.2 | 70.4 | 70.40 | 58 | 2100 | yes | no |
| cuda | standard_1080p | 2 | 24.8 | 80.6 | 40.30 | 71 | 2350 | yes | no |
| cuda | standard_1080p | 4 | 38.5 | 103.9 | 26.00 | 82 | 2800 | yes | no |
| cuda | standard_1080p | 8 | 46.1 | 173.5 | 21.70 | 88 | 3600 | yes | no |
| cuda | standard_1080p | 16 | 44.0 | 363.6 | 22.70 | 89 | 6200 | yes | no |
| cuda | standard_720p | 1 | 18.5 | 54.1 | 54.10 | 52 | 1800 | yes | no |
| cuda | standard_720p | 2 | 31.2 | 64.1 | 32.10 | 68 | 2000 | yes | no |
| cuda | standard_720p | 4 | 45.0 | 88.9 | 22.20 | 79 | 2400 | yes | no |
| cuda | standard_720p | 8 | 52.0 | 153.8 | 19.20 | 86 | 3100 | yes | no |
| cuda | standard_720p | 16 | 50.5 | 316.8 | 19.80 | 87 | 5200 | yes | no |
| cuda | standard_4k | 1 | 9.8 | 102.0 | 102.00 | 61 | 3200 | yes | no |
| cuda | standard_4k | 2 | 16.5 | 121.2 | 60.60 | 74 | 3800 | yes | no |
| cuda | standard_4k | 4 | 24.0 | 166.7 | 41.70 | 83 | 4600 | yes | no |
| cuda | standard_4k | 8 | 28.5 | 280.7 | 35.10 | 87 | 7200 | yes | no |
| cuda | standard_4k | 16 | 0.0 | 0.0 | 0.00 | n/a | n/a | no | yes |
| cpu | standard_1080p | 1 | 2.1 | 476.2 | 476.20 | n/a | n/a | yes | no |
| cpu | standard_1080p | 2 | 2.0 | 1000.0 | 500.00 | n/a | n/a | yes | no |
| cpu | standard_1080p | 4 | 1.8 | 2222.2 | 555.60 | n/a | n/a | yes | no |
| cpu | standard_1080p | 8 | 1.5 | 5333.3 | 666.70 | n/a | n/a | yes | no |
| cpu | standard_1080p | 16 | 1.2 | 13333.3 | 833.30 | n/a | n/a | yes | no |
| cpu | standard_720p | 1 | 2.8 | 357.1 | 357.10 | n/a | n/a | yes | no |
| cpu | standard_720p | 2 | 2.6 | 769.2 | 384.60 | n/a | n/a | yes | no |
| cpu | standard_720p | 4 | 2.3 | 1739.1 | 434.80 | n/a | n/a | yes | no |
| cpu | standard_720p | 8 | 2.0 | 4000.0 | 500.00 | n/a | n/a | yes | no |
| cpu | standard_720p | 16 | 1.6 | 10000.0 | 625.00 | n/a | n/a | yes | no |
| cpu | standard_4k | 1 | 1.4 | 714.3 | 714.30 | n/a | n/a | yes | no |
| cpu | standard_4k | 2 | 1.3 | 1538.5 | 769.20 | n/a | n/a | yes | no |
| cpu | standard_4k | 4 | 1.1 | 3636.4 | 909.10 | n/a | n/a | yes | no |
| cpu | standard_4k | 8 | 0.9 | 8888.9 | 1111.10 | n/a | n/a | yes | no |
| cpu | standard_4k | 16 | 0.7 | 22857.1 | 1428.60 | n/a | n/a | yes | no |

> Fixture timings are synthetic placeholders. Replace by running live
> commands on representative CPU and CUDA hosts.

## Recommended defaults by device class / profile

| device | profile | recommended batch | env override? | notes |
|--------|---------|------------------:|:-------------:|-------|
| cpu | standard_1080p | 1 | no | CPU workers should keep batch size 1. |
| cpu | standard_4k | 1 | no | CPU workers should keep batch size 1. |
| cpu | standard_720p | 1 | no | CPU workers should keep batch size 1. |
| cuda | standard_1080p | 2 | yes | Smallest batch size meeting 20.0% throughput or GPU-util threshold on profile standard_1080p. |
| cuda | standard_4k | 2 | yes | Smallest batch size meeting 20.0% throughput or GPU-util threshold on profile standard_4k. |
| cuda | standard_720p | 2 | yes | Smallest batch size meeting 20.0% throughput or GPU-util threshold on profile standard_720p. |

- Throughput threshold: `20.0%`
- Production default: `auto (8 on CUDA, 1 on CPU via runtime.py)`
- Change code default only after live benchmark: **yes**

