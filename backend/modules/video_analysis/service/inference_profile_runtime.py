from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

MINIMUM_CUDA_FP16_CAPABILITY = (5, 3)


def resolve_sahi_enabled(
    profile: Mapping[str, Any] | None,
    legacy_enabled: bool,
) -> bool:
    if not profile:
        return legacy_enabled
    enabled = bool(profile["sahi_enabled"])
    if enabled != legacy_enabled:
        raise RuntimeError("Persisted SAHI setting conflicts with the inference profile")
    return enabled


def resolve_precision_mode(
    requested: str,
    *,
    device: str,
    cuda_available: bool | None = None,
    cuda_capability: tuple[int, int] | None = None,
) -> Literal["fp32", "fp16"]:
    if requested == "fp32":
        return "fp32"
    if requested != "fp16":
        raise ValueError(f"Unsupported inference precision mode: {requested}")
    is_cuda_device = device.startswith("cuda") or device.isdigit()
    if not is_cuda_device:
        raise RuntimeError("FP16 inference requires an explicitly selected CUDA device")
    if cuda_available is None or cuda_capability is None:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("FP16 inference requires the PyTorch CUDA runtime") from exc
        cuda_available = torch.cuda.is_available()
        if cuda_available and cuda_capability is None:
            index = int(device) if device.isdigit() else int(device.partition(":")[2] or 0)
            cuda_capability = cast(tuple[int, int], torch.cuda.get_device_capability(index))
    if not cuda_available:
        raise RuntimeError("FP16 inference was requested but CUDA is unavailable")
    if cuda_capability is None or cuda_capability < MINIMUM_CUDA_FP16_CAPABILITY:
        raise RuntimeError("FP16 inference requires CUDA compute capability 5.3 or newer")
    return "fp16"


def precision_predict_options(precision_mode: str) -> dict[str, Any]:
    return {"quantize": "fp16"} if precision_mode == "fp16" else {}


def detector_options(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    return {
        "image_size": int(profile["image_size"]),
        "slice_height": int(profile["sahi_slice_height"]),
        "slice_width": int(profile["sahi_slice_width"]),
        "overlap_height_ratio": float(profile["sahi_overlap_height_ratio"]),
        "overlap_width_ratio": float(profile["sahi_overlap_width_ratio"]),
        "postprocess_match_threshold": float(profile["sahi_postprocess_match_threshold"]),
        "precision_mode": str(profile.get("precision_mode", "fp32")),
    }


def resolve_inference_batch_size(
    profile: Mapping[str, Any] | None,
    *,
    default: int,
) -> int:
    if not profile:
        return default
    return int(profile["batch_size"])
