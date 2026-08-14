from __future__ import annotations

import logging

from dronekit import VehicleMode

from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import logger
from backend.modules.vehicle_runtime.vehicle_port import MissionAbortRequested
from backend.observability.instruments import structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record


class MavlinkTakeoffMixin:
    """Arm, takeoff, and altitude feedback helpers."""

    def _current_takeoff_height_m(
        self,
        *,
        baseline_local_down: float | None,
        baseline_global_alt: float | None,
    ) -> tuple[float | None, str, dict[str, float]]:
        if not self.vehicle:
            return None, "unavailable", {}

        location = getattr(self.vehicle, "location", None)
        candidates: dict[str, float] = {}

        local = getattr(location, "local_frame", None)
        local_down = getattr(local, "down", None)
        if local_down is not None:
            baseline = float(baseline_local_down) if baseline_local_down is not None else 0.0
            # NED down becomes more negative as the drone climbs.
            candidates["local_ned"] = max(0.0, float(baseline) - float(local_down))

        rangefinder = getattr(self.vehicle, "rangefinder", None)
        rangefinder_distance = getattr(rangefinder, "distance", None)
        if rangefinder_distance is not None:
            candidates["rangefinder"] = max(0.0, float(rangefinder_distance))

        rel = getattr(location, "global_relative_frame", None)
        rel_alt = getattr(rel, "alt", None)
        if rel_alt is not None:
            candidates["global_relative"] = max(0.0, float(rel_alt))

        glob = getattr(location, "global_frame", None)
        glob_alt = getattr(glob, "alt", None)
        if glob_alt is not None and baseline_global_alt is not None:
            candidates["global_frame"] = max(0.0, float(glob_alt) - float(baseline_global_alt))

        if not candidates:
            return None, "unavailable", {}

        # Indoor-first source priority.
        for preferred in (
            "local_ned",
            "rangefinder",
            "global_relative",
            "global_frame",
        ):
            if preferred in candidates:
                return float(candidates[preferred]), preferred, candidates

        return None, "unavailable", candidates

    def arm_and_takeoff(self, alt: float) -> None:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")

        started = client_module().time.monotonic()
        target_alt_m = float(alt)
        with client_module().observed_span(
            "mavlink.takeoff",
            drone_id="mavlink",
            mavlink_command="takeoff",
            **{
                "mavlink.command.params": f"target_alt_m={target_alt_m:.2f}",
                "mavlink.ack.result": "unknown",
                "mavlink.retry_count": 0,
                "mavlink.timeout_ms": max(45.0, target_alt_m * 15.0) * 1000.0,
            },
        ):
            try:
                baseline_local_down = getattr(
                    getattr(getattr(self.vehicle, "location", None), "local_frame", None),
                    "down",
                    None,
                )
                baseline_global_alt = getattr(
                    getattr(getattr(self.vehicle, "location", None), "global_frame", None),
                    "alt",
                    None,
                )

                while not self.vehicle.is_armable:
                    client_module().time.sleep(1)

                self.vehicle.mode = VehicleMode("GUIDED")
                self.vehicle.armed = True

                while not self.vehicle.armed:
                    client_module().time.sleep(1)

                self.vehicle.simple_takeoff(target_alt_m)

                source_name = "unavailable"
                started_at = client_module().time.monotonic()
                timeout_s = max(45.0, target_alt_m * 15.0)
                last_candidates: dict[str, float] = {}
                next_progress_log_at = started_at + 5.0
                required_alt_m = max(target_alt_m * 0.92, target_alt_m - 0.35)
                stable_hits = 0
                stable_hits_required = 3

                while True:
                    if self._mission_abort_requested.is_set():
                        raise MissionAbortRequested("Operator abort requested during takeoff")

                    current_alt, source_name, last_candidates = self._current_takeoff_height_m(
                        baseline_local_down=baseline_local_down,
                        baseline_global_alt=baseline_global_alt,
                    )

                    if current_alt is not None and current_alt >= required_alt_m:
                        stable_hits += 1
                        if stable_hits >= stable_hits_required:
                            logger.info(
                                "Takeoff reached %.2fm using %s altitude feedback "
                                "(target=%.2fm, required=%.2fm)",
                                current_alt,
                                source_name,
                                target_alt_m,
                                required_alt_m,
                            )
                            break
                    else:
                        stable_hits = 0

                    now = client_module().time.monotonic()
                    if now >= next_progress_log_at:
                        logger.info(
                            "Takeoff progress %.2fm / %.2fm via %s | "
                            "required=%.2fm | candidates=%s",
                            float(current_alt or 0.0),
                            target_alt_m,
                            source_name,
                            required_alt_m,
                            {key: round(value, 2) for key, value in last_candidates.items()},
                        )
                        next_progress_log_at = now + 5.0

                    if now - started_at > timeout_s:
                        mode_name = (
                            getattr(getattr(self.vehicle, "mode", None), "name", None) or "UNKNOWN"
                        )
                        candidates_text = ", ".join(
                            f"{key}: {value:.2f}" for key, value in last_candidates.items()
                        )
                        metric_add("mavlink_timeouts", attrs={"command": "takeoff"})
                        raise TimeoutError(
                            "Timed out waiting for takeoff completion "
                            f"(target={target_alt_m:.2f}m, required={required_alt_m:.2f}m, "
                            f"source={source_name}, best={float(current_alt or 0.0):.2f}m, "
                            f"mode={mode_name}, candidates={{{candidates_text}}})"
                        )

                    self._mission_control_changed.wait(timeout=0.2)
                    self._mission_control_changed.clear()
                metric_record(
                    "mavlink_latency",
                    (client_module().time.monotonic() - started) * 1000.0,
                    {"command": "takeoff", "result": "success"},
                )
            except Exception as exc:
                metric_add("mavlink_failures", attrs={"command": "takeoff"})
                structured_error(
                    logger,
                    "mavlink_command_failed",
                    exc,
                    mavlink_command="takeoff",
                    latency_ms=(client_module().time.monotonic() - started) * 1000.0,
                )
                raise

