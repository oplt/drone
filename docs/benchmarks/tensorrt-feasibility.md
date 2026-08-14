# TensorRT feasibility decision

TASK 3.8 is gated on live proof that inference remains the dominant stage.

- Decision: **deferred**
- Prototype executed: **no**
- Production runtime changed: **no**
- Inference fraction: `0.6045340050377833`

## Blocking evidence

- Dominant-stage evidence is fixture-only, not a live target-worker run.
- FP16 accuracy/performance evidence is not from a live CUDA worker.

## Runtime measurements

| runtime | img/s | cold start ms | mAP50 | recall | artifact bytes |
|---|---:|---:|---:|---:|---:|

## Operational comparison

- **deployment_complexity** — PyTorch: Existing pinned worker image and portable .pt artifact. TensorRT: Adds TensorRT/CUDA compatibility and engine build operations.
- **model_management_burden** — PyTorch: One checksum-addressed production artifact. TensorRT: Engine artifact must be tied to model, precision, batch, GPU, and runtime versions.
- **rollback** — PyTorch: Current supported path. TensorRT: Keep PyTorch authoritative; an engine can only be an optional derivative.

The `.pt` runtime remains authoritative. A future engine is an optional,
checksum-addressed derivative only after all live gates pass.
