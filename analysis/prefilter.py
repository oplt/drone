from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np


@dataclass
class PreFilterConfig:
    """
    Thresholds for deciding whether a frame is "interesting" enough
    to send to the LLM.
    All deltas are measured vs. a moving average of previous frames.
    """
    delta_mean: float = 5.0           # brightness change
    delta_std: float = 5.0            # contrast / texture change
    delta_edge_density: float = 0.03  # edge density change (0..1)


class FramePreFilter:
    """
    Very cheap frame pre-filter:
    - convert to grayscale
    - compute mean brightness, std, and edge density
    - keep a moving average of these
    - if current frame deviates more than thresholds -> "interesting"
    """

    def __init__(self, cfg: Optional[PreFilterConfig] = None) -> None:
        self.cfg = cfg or PreFilterConfig()
        self._initialized = False

        self._mean: float = 0.0
        self._std: float = 0.0
        self._edge_density: float = 0.0

    def is_interesting(self, frame: np.ndarray) -> bool:
        """
        Returns True if the frame is different enough from the recent
        moving average to be worth sending to the LLM.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        mean = float(gray.mean())
        std = float(gray.std())

        # Edge density: roughly how many "structures" exist in the frame
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(edges.mean()) / 255.0  # normalize to 0..1

        if not self._initialized:
            # First frame: initialize baseline and analyze it
            self._mean = mean
            self._std = std
            self._edge_density = edge_density
            self._initialized = True
            return True

        # Deltas vs moving average
        delta_mean = abs(mean - self._mean)
        delta_std = abs(std - self._std)
        delta_edge = abs(edge_density - self._edge_density)

        # Update moving averages (smooth 0.9 older, 0.1 new)
        alpha = 0.9
        self._mean = alpha * self._mean + (1.0 - alpha) * mean
        self._std = alpha * self._std + (1.0 - alpha) * std
        self._edge_density = alpha * self._edge_density + (1.0 - alpha) * edge_density

        # Decide if this frame is interesting
        if (
            delta_mean >= self.cfg.delta_mean
            or delta_std >= self.cfg.delta_std
            or delta_edge >= self.cfg.delta_edge_density
        ):
            return True

        return False
