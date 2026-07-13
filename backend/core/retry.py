"""Shared bounded retry delay policy."""

from __future__ import annotations

import math
import random
from typing import cast


def retry_delay_seconds(
    *,
    attempt: int,
    base_seconds: float = 30.0,
    max_seconds: float = 900.0,
    jitter_ratio: float = 0.2,
) -> int:
    """Return exponential backoff with bounded random jitter."""
    exponent = max(0, int(attempt))
    upper_bound = max(1, int(max_seconds))
    delay = min(float(upper_bound), max(0.0, float(base_seconds)) * (2**exponent))
    jitter = max(0.0, min(1.0, float(jitter_ratio)))
    jittered = math.floor(delay * random.uniform(1.0 - jitter, 1.0 + jitter) + 0.5)
    return cast(int, max(1, min(upper_bound, jittered)))
