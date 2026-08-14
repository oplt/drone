# Video inference precision benchmark

TASK 3.7 compares FP32 and opt-in FP16 accuracy and throughput.

- Mode: `fixture`
- Model checksum: `sha256:replace-with-production-model-checksum`
- Production default: `fp32`

| precision | img/s | batch ms | mAP50 | recall | supported | stable |
|---|---:|---:|---:|---:|:---:|:---:|
| fp32 | 40.00 | 200.00 | 0.7000 | 0.7200 | yes | yes |
| fp16 | 54.00 | 148.10 | 0.6980 | 0.7180 | yes | yes |

## Decision

- Promote FP16: **no**
- Reason: Fixture data cannot promote FP16; run on the target CUDA worker.

Fixture measurements are synthetic and cannot change production defaults.
Run live on the target CUDA worker with an audited validation dataset.
