# Agriculture vision models

The `vision_models` module owns crop-specific projects, immutable dataset
versions, original-image detection annotations, asynchronous Ultralytics
training/evaluation, and the versioned model registry. Every query is scoped to
the authenticated organization, or to the creating user when no organization
is assigned.

## Workflow

1. Create a project with a canonical Agriculture capability, crop, and ordered
   detection classes.
2. Create a dataset and upload images, or curate frames from an authorized
   mission recording. Curation rejects corrupt, tiny, blurry, badly exposed,
   and perceptually duplicated frames while preserving a manifest.
3. Label images in the lazy-loaded Konva workspace. Bounding boxes are stored
   in original-image pixels, never viewport coordinates. Images with no target
   objects can be marked reviewed with zero boxes.
4. Review every selected image and start a training run. The dataset is locked,
   deterministic leakage-safe train/validation/test splits are persisted, and
   work is queued to the dedicated `vision-training` Celery worker.
5. Ultralytics trains from the managed YOLO export and evaluates `best.pt`
   against the test split. Precision, recall, F1, mAP50, mAP75, mAP50–95,
   per-class values, confusion data, evaluator-provided per-image failures, and
   generated plots are persisted on the model version. Metrics are read from
   evaluator objects, not parsed from console output.
6. Inspect or compare versions in the evaluation dashboard, then explicitly
   deploy a candidate. The previous production version returns to candidate
   status; historical weights and metrics remain available. Deployment also
   activates the tenant's Agriculture capability release without copying the
   artifact. See [ADR-001](adr-001-vision-artifact-agriculture-capability-release.md).

## Labeling persistence

The client saves through a serialized mutation queue. Draw, move, resize,
reclassify, delete, and review changes are optimistic, but navigation waits for
the queue. Failed saves remain visible and prevent silent image changes. The
backend validates finite, ordered coordinates against the original image
dimensions and rejects classes outside the project.

YOLO imports convert normalized labels into original-image pixels. YOLO exports
and training preparation convert those pixels back to normalized values at the
format boundary. The managed `vision://` storage adapter is the only supported
path for source media, manifests, weights, and evaluation artifacts.

## Video inference integration

Video jobs may select a production `model_version_id`; arbitrary client file
paths are never accepted. The job persists the resolved model version and
checksum for reproducibility.

`tracking_enabled` creates one job-local, class-aware ByteTrack instance.
Track IDs are translated into a job-scoped global ID space and persisted with
each detection. Tracking requires a sampling interval of at most two seconds.
The summary endpoint reports detections and distinct tracks by class, confidence
distribution, and the exact model/tracking/inference flags used.

`small_object_mode` selects the SAHI detector. It performs 640×640 sliced
inference with 20% overlap, includes a standard full-frame prediction, merges
with class-aware NMS at IoU 0.5, and returns coordinates in the original frame.
Slice settings live in runtime configuration. SAHI initialization or inference
failure fails the job explicitly; it never falls back silently to standard
inference.

## Operations

- API routes are mounted under `/vision`; video summaries are under
  `/video-analysis/jobs/{job_id}/summary`.
- `worker-vision` consumes only the `vision-training` queue at concurrency one.
- CPU training works but is expected to be slow; production deployments should
  configure an accelerator and suitable worker limits.
- Training run status is `queued`, `running`, `cancelling`, `completed`,
  `failed`, or `cancelled`. A model version exists only after evaluation completes, so its
  evaluation resource is always `completed`; failed evaluation remains on the
  training run with its persisted error.
- Missing media, weights, and evaluation artifacts return 404. Missing SAHI or
  training dependencies produce actionable job failures.

## Dependency choices

The frontend pins React-Konva 19.2.5 and Konva 10.3.0 for React 19. The backend
pins SAHI 0.11.36 because SAHI 0.12 requires OpenCV 4.12+, while this deployment
uses OpenCV 4.9 and the installed Ultralytics generation. The annotation route
and its Konva vendor chunk are lazy-loaded and do not increase the initial
Agriculture page bundle.
