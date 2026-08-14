# Vision training dataloader worker benchmark

Ultralytics `workers` argument for YOLO training. Default remains `VISION_TRAINING_DATALOADER_WORKERS=0` unless live results on your GPU host meet the adoption threshold.

## Runbook

Fixture (no GPU):

```sh
python3 backend/scripts/benchmarks/run_vision_training_dataloader_benchmark.py \
  --fixture --output docs/benchmarks/vision-training-dataloader-report.json
```

Live (torch + ultralytics + optional NVIDIA GPU):

```sh
python3 backend/scripts/benchmarks/run_vision_training_dataloader_benchmark.py \
  --output /tmp/vision-dataloader-report.json
python3 backend/scripts/benchmarks/run_vision_training_dataloader_benchmark.py \
  --render-markdown /tmp/vision-dataloader-report.json \
  --markdown-output docs/benchmarks/vision-training-dataloader.md
```

- Mode: `fixture`
- Manifest: `vision-training-dataloader-representative`
- Model: `yolo26n.pt`
- Benchmark epochs per worker setting: `1`

## Results

| workers | epoch_s | GPU util avg % | CPU util avg % | RAM peak MiB | stable |
|--------:|--------:|---------------:|---------------:|-------------:|:------:|
| 0 | 42.5 | 62 | 28 | 6.6 | yes |
| 2 | 36.1 | 74 | 41 | 6.9 | yes |
| 4 | 35.4 | 76 | 48 | 7.4 | yes |

## Adoption analysis

- Baseline workers: `0`
- Best workers: `4`
- Best improvement vs baseline: `16.71%`
- Threshold: `15.0%` epoch-time improvement or materially higher GPU occupancy
- Recommend opt-in on GPU training host: **yes**
- Suggested env for that host: `VISION_TRAINING_DATALOADER_WORKERS=2`
- Code default stays: `0` (set env on vision-training worker only)
- Notes: Smallest worker count meeting adoption threshold on this host

## Guidance

- **CPU / macOS / Windows / low RAM**: keep `0`.
- **Linux + NVIDIA GPU**: benchmark locally; if workers `2` saves ~15%+ epoch time with stable runs, set env on the vision-training worker only.
- Workers `4` rarely beats `2` unless CPU and RAM headroom are large.
- Record live JSON alongside this doc after hardware changes.

> Fixture timings are synthetic placeholders. Replace by running the live command on the target training host.
