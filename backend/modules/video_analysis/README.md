# Offline Video Analysis Module

## Add router

In `backend/entrypoints/api/app.py`, include:

```python
from backend.modules.video_analysis.api import router as video_analysis_router
app.include_router(video_analysis_router)
```

## Ensure Celery imports the task

If your `entrypoints/workers/celery_app.py` does not autodiscover tasks, add:

```python
from backend.entrypoints.workers import video_analysis_tasks  # noqa: F401
```

## Install dependencies

For headless Linux backend:

```bash
pip install -U ultralytics-opencv-headless opencv-python-headless supervision trackers
```

For CUDA, install the correct PyTorch wheel first from pytorch.org, then install Ultralytics.

## Prewarm model downloads

```bash
python backend/scripts/download_video_analysis_models.py
```

Built-in weights are stored under `backend/storage/ml_models/ultralytics/`.
When a built-in weight is missing, the worker downloads it directly into this directory before loading it.
Custom API values such as `storage/ml_models/agriculture/best.pt` resolve to
`backend/storage/ml_models/agriculture/best.pt` on disk.

## API flow

1. Upload video:
```bash
curl -F "file=@flight.mp4" -F "mission_id=<mission_id>" http://localhost:8000/video-analysis/videos
```

2. Start analysis:
```bash
curl -X POST http://localhost:8000/video-analysis/videos/<video_id>/analyze \
  -H "Content-Type: application/json" \
  -d '{"model_name":"yolo26s.pt","frame_stride_seconds":1.0,"confidence_threshold":0.35}'
```

3. Poll job:
```bash
curl http://localhost:8000/video-analysis/jobs/<job_id>
```

4. Get detections:
```bash
curl http://localhost:8000/video-analysis/jobs/<job_id>/detections
```

## Smoke test

```bash
python backend/scripts/smoke_test_video_analysis.py /path/to/test_video.mp4
```
