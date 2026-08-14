from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

ProgressCallback = Callable[[int, int, dict[str, float]], None]


@dataclass(frozen=True)
class TrainerRequest:
    base_model: str
    data_config: Path
    output_dir: Path
    epochs: int
    image_size: int
    batch_size: int
    requested_device: str
    class_names: list[str]
    dataloader_workers: int = 0


@dataclass(frozen=True)
class TrainerResult:
    best_weights: Path
    device: str
    metrics: dict[str, object]
    evaluation_artifacts: dict[str, Path] = field(default_factory=dict)


class Trainer(Protocol):
    def train(
        self,
        request: TrainerRequest,
        progress_callback: ProgressCallback,
    ) -> TrainerResult: ...
