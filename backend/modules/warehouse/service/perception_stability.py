from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from backend.modules.warehouse.service.flight_health import SubsystemHealth, SubsystemStatus

logger = logging.getLogger(__name__)

CORE_TOPIC_KEYS = ("rgb_image", "depth", "imu", "visual_slam_odom")


def diagnostics_probe_pending(components: dict[str, object]) -> bool:
    if components.get("diagnostics_pending"):
        return True
    return bool(
        components.get("probe_in_progress") and not components.get("cache_ready", True)
    )


def perception_core_ok(
    *,
    bridge: SubsystemHealth,
    sensors: SubsystemHealth,
    slam: SubsystemHealth,
    nvblox: SubsystemHealth,
    components: dict[str, object],
    require_nvblox: bool,
    mapping_stack_running: bool = False,
) -> bool:
    if diagnostics_probe_pending(components):
        return False
    if bridge.status != SubsystemStatus.OK:
        return False
    if sensors.status == SubsystemStatus.FAIL:
        return False
    if slam.status == SubsystemStatus.FAIL:
        return False
    if require_nvblox and mapping_stack_running and nvblox.status != SubsystemStatus.OK:
        if (
            nvblox.status == SubsystemStatus.WAITING
            and components.get("nvblox_warming_up")
        ):
            return True
        return False
    return True


@dataclass
class PerceptionStabilityTracker:
    """Requires core warehouse perception to pass continuously before flight."""

    _stable_since: float | None = field(default=None, init=False, repr=False)
    _last_ok: bool = field(default=False, init=False, repr=False)
    _last_log_at: float = field(default=0.0, init=False, repr=False)
    _last_reset_reason: str | None = field(default=None, init=False, repr=False)
    _last_stable_ms: int = field(default=0, init=False, repr=False)

    @property
    def last_reset_reason(self) -> str | None:
        return self._last_reset_reason

    @property
    def last_successful_stable_ms(self) -> int:
        return self._last_stable_ms

    def reset(self, *, reason: str | None = None) -> None:
        if self._stable_since is not None:
            self._last_stable_ms = max(
                self._last_stable_ms,
                max(0, int((time.monotonic() - self._stable_since) * 1000.0)),
            )
        self._stable_since = None
        self._last_ok = False
        if reason:
            self._last_reset_reason = reason

    def hold_stable_ms(self) -> int:
        """Return accumulated stable time without starting or resetting the window."""
        if self._stable_since is None:
            return 0
        return max(0, int((time.monotonic() - self._stable_since) * 1000.0))

    def stable_for_ms(
        self,
        *,
        perception_ok: bool,
        reset_reason: str | None = None,
    ) -> int:
        now = time.monotonic()
        if perception_ok:
            if self._stable_since is None:
                self._stable_since = now
                self._last_reset_reason = None
                logger.info("Perception stability window started")
            self._last_ok = True
        else:
            if self._last_ok or self._stable_since is not None:
                if self._stable_since is not None:
                    self._last_stable_ms = max(
                        self._last_stable_ms,
                        max(0, int((now - self._stable_since) * 1000.0)),
                    )
                reason = reset_reason or self._last_reset_reason or "core perception not OK"
                self._last_reset_reason = reason
                logger.info("Perception stability window reset: %s", reason)
            self._stable_since = None
            self._last_ok = False

        if self._stable_since is None:
            return 0
        return max(0, int((now - self._stable_since) * 1000.0))

    def maybe_log_progress(self, *, stable_ms: int, required_ms: int) -> None:
        now = time.monotonic()
        if now - self._last_log_at < 5.0:
            return
        self._last_log_at = now
        if 0 < stable_ms < required_ms:
            logger.info(
                "Perception stability progress stable_for_ms=%s required_ms=%s",
                stable_ms,
                required_ms,
            )


_PERCEPTION_STABILITY = PerceptionStabilityTracker()


def get_perception_stability_tracker() -> PerceptionStabilityTracker:
    return _PERCEPTION_STABILITY
