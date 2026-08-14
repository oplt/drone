#!/usr/bin/env python3
"""TASK 3.8 gated one-model TensorRT feasibility runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS_DIR = Path(__file__).resolve().parent
for path in (str(REPO_ROOT), str(BENCHMARKS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from inference_batch_benchmark import generate_synthetic_images  # noqa: E402
from precision_benchmark import metric_value  # noqa: E402
from tensorrt_feasibility import (  # noqa: E402
    analyze_runtime_comparison,
    evaluate_prerequisites,
    operational_comparison,
)

from backend.modules.video_analysis.model_storage import ensure_model_file  # noqa: E402
from backend.modules.video_analysis.service.inference_profile_runtime import (  # noqa: E402
    precision_predict_options,
    resolve_precision_mode,
)

DEFAULT_MANIFEST = Path(__file__).with_name("tensorrt_feasibility_manifest.example.json")
DEFAULT_OUTPUT = REPO_ROOT / "docs/benchmarks/tensorrt-feasibility-report.json"
DEFAULT_MARKDOWN = REPO_ROOT / "docs/benchmarks/tensorrt-feasibility.md"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if int(payload.get("version", -1)) != 1:
        raise SystemExit(f"Unsupported manifest version: {payload.get('version')!r}")
    for key in ("model_name", "performance_report", "precision_report", "gates"):
        if key not in payload:
            raise SystemExit(f"Manifest missing required key: {key}")
    return payload


def _resolved_report_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _sync_cuda() -> None:
    import torch

    torch.cuda.synchronize()


def _runtime_row(
    model_source: Path,
    *,
    runtime: str,
    manifest: dict[str, Any],
    images: list[Any],
) -> dict[str, Any]:
    from ultralytics import YOLO

    started = time.monotonic()
    model = YOLO(str(model_source))
    options = precision_predict_options("fp16") if runtime == "pytorch_fp16" else {}
    predict = {
        "source": images,
        "imgsz": int(manifest.get("image_size", 640)),
        "device": str(manifest.get("device", "cuda:0")),
        "verbose": False,
        **options,
    }
    model.predict(**predict)
    _sync_cuda()
    cold_start_ms = (time.monotonic() - started) * 1000.0
    for _ in range(int(manifest.get("warmup_batches", 2))):
        model.predict(**predict)
    _sync_cuda()
    timed_batches = int(manifest.get("timed_batches", 10))
    started = time.monotonic()
    for _ in range(timed_batches):
        model.predict(**predict)
    _sync_cuda()
    elapsed = time.monotonic() - started
    validation_data = manifest.get("validation_data")
    if not validation_data:
        raise RuntimeError("TensorRT feasibility requires validation_data")
    validation = model.val(
        data=str(validation_data),
        imgsz=int(manifest.get("image_size", 640)),
        batch=int(manifest.get("batch_size", 1)),
        device=str(manifest.get("device", "cuda:0")),
        verbose=False,
        **options,
    )
    metrics = dict(getattr(validation, "results_dict", {}) or {})
    return {
        "runtime": runtime,
        "stable": True,
        "cold_start_ms": cold_start_ms,
        "images_per_second": len(images) * timed_batches / elapsed,
        "map50": metric_value(metrics, "metrics/mAP50(B)", "metrics/mAP50"),
        "recall": metric_value(metrics, "metrics/recall(B)", "metrics/recall"),
        "artifact_bytes": model_source.stat().st_size,
        "artifact_checksum": hashlib.sha256(model_source.read_bytes()).hexdigest(),
    }


def run_prototype(
    manifest: dict[str, Any], workspace: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    device = str(manifest.get("device", "cuda:0"))
    resolve_precision_mode("fp16", device=device)
    source = ensure_model_file(str(manifest["model_name"]))
    source_checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    expected = str(manifest.get("model_checksum") or "")
    if expected and not expected.startswith("replace-") and expected != source_checksum:
        raise RuntimeError("Production model checksum does not match the manifest")
    workspace.mkdir(parents=True, exist_ok=True)
    local_weights = workspace / source.name
    shutil.copy2(source, local_weights)
    from ultralytics import YOLO

    export_model = YOLO(str(local_weights))
    exported = Path(
        export_model.export(
            format="engine",
            device=int(device.partition(":")[2] or 0),
            imgsz=int(manifest.get("image_size", 640)),
            batch=int(manifest.get("batch_size", 1)),
            workspace=float(manifest.get("workspace_gib", 4.0)),
            quantize="fp16",
        )
    )
    images = generate_synthetic_images(
        int(manifest.get("batch_size", 1)),
        width=int(manifest.get("source_width", 1920)),
        height=int(manifest.get("source_height", 1080)),
        seed=11,
    )
    rows = [
        _runtime_row(
            local_weights,
            runtime="pytorch_fp16",
            manifest=manifest,
            images=images,
        ),
        _runtime_row(
            exported,
            runtime="tensorrt_fp16",
            manifest=manifest,
            images=images,
        ),
    ]
    return rows, {
        "workspace": str(workspace),
        "source_model_checksum": source_checksum,
        "engine_path": str(exported),
        "production_runtime_changed": False,
    }


def build_report(
    manifest: dict[str, Any],
    prerequisites: dict[str, Any],
    *,
    rows: list[dict[str, Any]] | None = None,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = rows or []
    gates = manifest["gates"]
    comparison = (
        analyze_runtime_comparison(
            rows,
            mode="live",
            minimum_throughput_improvement_percent=float(
                gates["minimum_throughput_improvement_percent"]
            ),
            max_map50_regression=float(gates["max_map50_regression"]),
            max_recall_regression=float(gates["max_recall_regression"]),
        )
        if rows
        else {
            "adopt_tensorrt": False,
            "reason": "Experiment deferred until prerequisite profiling is live.",
        }
    )
    return {
        "version": 1,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "decision": "evaluated" if rows else "deferred",
        "prototype_executed": bool(rows),
        "prerequisites": prerequisites,
        "rows": rows,
        "comparison": comparison,
        "operational_comparison": operational_comparison(),
        "artifact": artifact,
        "production_runtime_changed": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    prerequisites = report["prerequisites"]
    lines = [
        "# TensorRT feasibility decision",
        "",
        "TASK 3.8 is gated on live proof that inference remains the dominant stage.",
        "",
        f"- Decision: **{report['decision']}**",
        f"- Prototype executed: **{'yes' if report['prototype_executed'] else 'no'}**",
        f"- Production runtime changed: **{'yes' if report['production_runtime_changed'] else 'no'}**",
        f"- Inference fraction: `{prerequisites['dominance']['inference_fraction']}`",
        "",
    ]
    if prerequisites["reasons"]:
        lines.extend(["## Blocking evidence", ""])
        lines.extend(f"- {reason}" for reason in prerequisites["reasons"])
        lines.append("")
    lines.extend(
        [
            "## Runtime measurements",
            "",
            "| runtime | img/s | cold start ms | mAP50 | recall | artifact bytes |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| {runtime} | {ips:.2f} | {cold:.2f} | {map50:.4f} | {recall:.4f} | {size} |".format(
                runtime=row["runtime"],
                ips=float(row.get("images_per_second") or 0.0),
                cold=float(row.get("cold_start_ms") or 0.0),
                map50=float(row.get("map50") or 0.0),
                recall=float(row.get("recall") or 0.0),
                size=int(row.get("artifact_bytes") or 0),
            )
        )
    lines.extend(["", "## Operational comparison", ""])
    for item in report["operational_comparison"]:
        lines.append(
            f"- **{item['criterion']}** — PyTorch: {item['pytorch']} TensorRT: {item['tensorrt']}"
        )
    lines.extend(
        [
            "",
            "The `.pt` runtime remains authoritative. A future engine is an optional,",
            "checksum-addressed derivative only after all live gates pass.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--workspace", type=Path, default=Path("/tmp/drone-tensorrt-feasibility"))
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    performance = load_json(_resolved_report_path(manifest["performance_report"]))
    precision = load_json(_resolved_report_path(manifest["precision_report"]))
    prerequisites = evaluate_prerequisites(
        performance,
        precision,
        minimum_inference_fraction=float(manifest["gates"]["minimum_inference_fraction"]),
    )
    rows: list[dict[str, Any]] = []
    artifact = None
    if prerequisites["eligible"]:
        rows, artifact = run_prototype(manifest, args.workspace)
    report = build_report(manifest, prerequisites, rows=rows, artifact=artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_markdown(report))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
