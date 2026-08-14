"""Core helpers for TASK 3.4 video inference batch-size benchmarks."""

from __future__ import annotations

import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


def batch_key(batch_size: int) -> str:
    return str(int(batch_size))


def detect_device_class() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def resolve_device_label(device_class: str) -> str:
    if device_class != "cuda":
        return "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            return f"cuda:0"
    except ImportError:
        pass
    return "cpu"


def generate_synthetic_images(
    count: int,
    *,
    width: int,
    height: int,
    seed: int = 0,
) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    return [
        rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
        for _ in range(count)
    ]


def _query_gpu_utilization_pct() -> float | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        line = completed.stdout.strip().splitlines()[0].strip()
        return float(line)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _query_gpu_memory_used_mb() -> float | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        line = completed.stdout.strip().splitlines()[0].strip()
        return float(line)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None


@dataclass
class ResourceSamples:
    cpu_util_avg_pct: float | None = None
    ram_peak_mb: float | None = None
    gpu_util_avg_pct: float | None = None
    vram_peak_mb: float | None = None
    _cpu: list[float] = field(default_factory=list)
    _ram_mb: list[float] = field(default_factory=list)
    _gpu: list[float] = field(default_factory=list)
    _vram_mb: list[float] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _sample_loop(self) -> None:
        import psutil

        while not self._stop.is_set():
            self._cpu.append(float(psutil.cpu_percent(interval=None)))
            self._ram_mb.append(float(psutil.virtual_memory().used) / (1024 * 1024))
            gpu = _query_gpu_utilization_pct()
            if gpu is not None:
                self._gpu.append(gpu)
            vram = _query_gpu_memory_used_mb()
            if vram is not None:
                self._vram_mb.append(vram)
            time.sleep(0.5)

    def finalize(self) -> None:
        self.cpu_util_avg_pct = statistics.mean(self._cpu) if self._cpu else None
        self.ram_peak_mb = max(self._ram_mb) if self._ram_mb else None
        self.gpu_util_avg_pct = statistics.mean(self._gpu) if self._gpu else None
        self.vram_peak_mb = max(self._vram_mb) if self._vram_mb else None


@dataclass(frozen=True)
class BatchBenchmarkResult:
    batch_size: int
    available: bool = True
    stable: bool = True
    oom: bool = False
    images_per_second: float = 0.0
    batch_latency_ms: float = 0.0
    per_image_latency_ms: float = 0.0
    gpu_util_avg_pct: float | None = None
    vram_peak_mb: float | None = None
    ram_peak_mb: float | None = None
    timed_batches: int = 0
    total_images: int = 0
    error: str | None = None


def _is_oom_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if "out of memory" in message or "cuda error" in message and "memory" in message:
        return True
    try:
        import torch

        return isinstance(exc, torch.cuda.OutOfMemoryError)
    except ImportError:
        return False


def benchmark_batch_size_live(
    *,
    model: Any,
    images: list[np.ndarray],
    batch_size: int,
    device: str,
    confidence_threshold: float,
    warmup_batches: int,
    timed_batches: int,
) -> BatchBenchmarkResult:
    if batch_size < 1 or not images:
        return BatchBenchmarkResult(
            batch_size=batch_size,
            available=False,
            stable=False,
            error="invalid batch_size or empty image set",
        )

    def _run_batch(batch: list[np.ndarray]) -> None:
        model.predict(
            source=batch,
            conf=confidence_threshold,
            device=device,
            verbose=False,
        )

    try:
        import torch
    except ImportError:
        torch = None  # type: ignore[assignment]

    if torch is not None and device.startswith("cuda"):
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    sampler = ResourceSamples()
    batch_latencies_ms: list[float] = []
    total_images = 0
    oom = False
    error: str | None = None
    stable = True

    try:
        for _ in range(warmup_batches):
            batch = images[:batch_size]
            _run_batch(batch)

        sampler.start()
        started = time.monotonic()
        for _ in range(timed_batches):
            batch = images[:batch_size]
            batch_started = time.monotonic()
            _run_batch(batch)
            batch_latencies_ms.append((time.monotonic() - batch_started) * 1000.0)
            total_images += len(batch)
        wall_seconds = time.monotonic() - started
    except Exception as exc:
        stable = False
        oom = _is_oom_error(exc)
        error = str(exc)
        wall_seconds = 0.0
    finally:
        sampler.stop()
        sampler.finalize()

    vram_peak_mb = sampler.vram_peak_mb
    if torch is not None and device.startswith("cuda") and torch.cuda.is_available():
        vram_peak_mb = max(
            vram_peak_mb or 0.0,
            float(torch.cuda.max_memory_allocated()) / (1024 * 1024),
        )

    if oom or not stable:
        return BatchBenchmarkResult(
            batch_size=batch_size,
            available=not oom,
            stable=False,
            oom=oom,
            gpu_util_avg_pct=sampler.gpu_util_avg_pct,
            vram_peak_mb=vram_peak_mb,
            ram_peak_mb=sampler.ram_peak_mb,
            error=error,
        )

    images_per_second = total_images / wall_seconds if wall_seconds > 0 else 0.0
    batch_latency_ms = (
        statistics.mean(batch_latencies_ms) if batch_latencies_ms else 0.0
    )
    per_image_latency_ms = batch_latency_ms / batch_size if batch_size > 0 else 0.0

    return BatchBenchmarkResult(
        batch_size=batch_size,
        images_per_second=round(images_per_second, 3),
        batch_latency_ms=round(batch_latency_ms, 3),
        per_image_latency_ms=round(per_image_latency_ms, 3),
        gpu_util_avg_pct=sampler.gpu_util_avg_pct,
        vram_peak_mb=round(vram_peak_mb, 1) if vram_peak_mb is not None else None,
        ram_peak_mb=round(sampler.ram_peak_mb, 1) if sampler.ram_peak_mb else None,
        timed_batches=timed_batches,
        total_images=total_images,
    )


def row_from_result(
    *,
    device_class: str,
    profile: dict[str, Any],
    batch_size: int,
    result: dict[str, Any] | BatchBenchmarkResult,
) -> dict[str, Any]:
    payload = (
        result
        if isinstance(result, dict)
        else {
            "available": result.available,
            "stable": result.stable,
            "oom": result.oom,
            "images_per_second": result.images_per_second,
            "batch_latency_ms": result.batch_latency_ms,
            "per_image_latency_ms": result.per_image_latency_ms,
            "gpu_util_avg_pct": result.gpu_util_avg_pct,
            "vram_peak_mb": result.vram_peak_mb,
            "ram_peak_mb": result.ram_peak_mb,
            "timed_batches": result.timed_batches,
            "total_images": result.total_images,
            "error": result.error,
        }
    )
    return {
        "device_class": device_class,
        "profile_id": profile["id"],
        "profile_label": profile.get("label", profile["id"]),
        "width": int(profile.get("width", 640)),
        "height": int(profile.get("height", 480)),
        "imgsz": int(profile.get("imgsz", 640)),
        "batch_size": int(batch_size),
        "available": bool(payload.get("available", True)),
        "stable": bool(payload.get("stable", True)),
        "oom": bool(payload.get("oom", False)),
        "images_per_second": float(payload.get("images_per_second", 0.0)),
        "batch_latency_ms": float(payload.get("batch_latency_ms", 0.0)),
        "per_image_latency_ms": float(payload.get("per_image_latency_ms", 0.0)),
        "gpu_util_avg_pct": payload.get("gpu_util_avg_pct"),
        "vram_peak_mb": payload.get("vram_peak_mb"),
        "ram_peak_mb": payload.get("ram_peak_mb"),
        "timed_batches": int(payload.get("timed_batches", 0)),
        "total_images": int(payload.get("total_images", 0)),
        "error": payload.get("error"),
    }


def build_fixture_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    fixture = dict(manifest.get("fixture") or {})
    device_classes = list(manifest.get("fixture_device_classes") or [])
    if not device_classes:
        device_classes = [str(manifest.get("hardware", {}).get("device_class", "cuda"))]
    rows: list[dict[str, Any]] = []
    for device_class in device_classes:
        device_fixture = dict(fixture.get(device_class) or {})
        for profile in manifest["profiles"]:
            profile_id = str(profile["id"])
            profile_fixture = dict(device_fixture.get(profile_id) or {})
            for batch_size in manifest["batch_sizes"]:
                key = batch_key(batch_size)
                row = dict(profile_fixture.get(key) or profile_fixture.get(batch_size) or {})
                if not row:
                    raise SystemExit(
                        f"Fixture missing device={device_class} profile={profile_id} batch={batch_size}"
                    )
                rows.append(
                    row_from_result(
                        device_class=device_class,
                        profile=profile,
                        batch_size=int(batch_size),
                        result=row,
                    )
                )
    return rows


def analyze_recommendations(
    rows: list[dict[str, Any]],
    *,
    throughput_threshold_percent: float = 20.0,
    gpu_util_delta_threshold: float = 10.0,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["device_class"]), str(row["profile_id"]))
        grouped.setdefault(key, {})[int(row["batch_size"])] = row

    recommendations: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []

    for (device_class, profile_id), batches in sorted(grouped.items()):
        baseline = batches.get(1)
        if baseline is None:
            continue
        base_ips = float(baseline.get("images_per_second") or 0.0)
        base_gpu = baseline.get("gpu_util_avg_pct")
        profile_label = baseline.get("profile_label", profile_id)

        if device_class == "cpu":
            recommendations.append(
                {
                    "device_class": device_class,
                    "profile_id": profile_id,
                    "profile_label": profile_label,
                    "recommended_batch_size": 1,
                    "recommend_env_override": False,
                    "reason": "CPU workers should keep batch size 1.",
                }
            )
            continue

        recommended = 1
        reason = "Batch size 1 is safest default without live GPU validation."
        for batch_size in sorted(batches):
            row = batches[batch_size]
            if batch_size == 1:
                continue
            if not row.get("stable", True) or row.get("oom"):
                comparisons.append(
                    {
                        "device_class": device_class,
                        "profile_id": profile_id,
                        "batch_size": batch_size,
                        "throughput_improvement_percent": None,
                        "meets_threshold": False,
                        "oom": bool(row.get("oom")),
                        "stable": bool(row.get("stable", True)),
                    }
                )
                continue
            ips = float(row.get("images_per_second") or 0.0)
            throughput_improve = (
                ((ips - base_ips) / base_ips) * 100.0 if base_ips > 0 else 0.0
            )
            gpu_ok = (
                row.get("gpu_util_avg_pct") is not None
                and base_gpu is not None
                and float(row["gpu_util_avg_pct"]) - float(base_gpu)
                >= gpu_util_delta_threshold
            )
            meets = throughput_improve >= throughput_threshold_percent or gpu_ok
            comparisons.append(
                {
                    "device_class": device_class,
                    "profile_id": profile_id,
                    "batch_size": batch_size,
                    "throughput_improvement_percent": round(throughput_improve, 2),
                    "gpu_util_avg_pct": row.get("gpu_util_avg_pct"),
                    "meets_threshold": meets,
                    "oom": False,
                    "stable": True,
                }
            )
            if meets and recommended == 1:
                recommended = batch_size
                reason = (
                    f"Smallest batch size meeting {throughput_threshold_percent}% "
                    f"throughput or GPU-util threshold on profile {profile_id}."
                )

        recommendations.append(
            {
                "device_class": device_class,
                "profile_id": profile_id,
                "profile_label": profile_label,
                "recommended_batch_size": recommended,
                "recommend_env_override": recommended != 8,
                "reason": reason,
            }
        )

    return {
        "throughput_threshold_percent": throughput_threshold_percent,
        "gpu_util_delta_threshold": gpu_util_delta_threshold,
        "recommendations": recommendations,
        "comparisons": comparisons,
        "production_default_batch_size": "auto (8 on CUDA, 1 on CPU via runtime.py)",
        "change_default_only_after_live_benchmark": True,
    }
