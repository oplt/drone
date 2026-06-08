from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from backend.core.config.runtime import settings
from backend.modules.preflight.checks.schemas import CheckStatus
from backend.modules.preflight.checks.service import PreflightOrchestrator
from backend.modules.vehicle_runtime.types import Coordinate

logger = logging.getLogger(__name__)


class RuntimeRecoveryServiceMixin:
    async def _raw_event_ingest_worker(self):
        BATCH_SIZE = 1000
        INTERVAL_S = 0.25
        buffer = []
        logger.info("Starting _raw_event_ingest_worker")

        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(self._raw_event_queue.get(), timeout=INTERVAL_S)
                    buffer.append(item)

                    # drain quickly
                    while len(buffer) < BATCH_SIZE:
                        try:
                            buffer.append(self._raw_event_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                    if self._flight_id is None:
                        buffer.clear()
                        continue

                    if buffer:
                        try:
                            await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        except Exception:
                            logger.exception(
                                "Raw event ingest worker: DB write failed; "
                                "batch of %d rows dropped",
                                len(buffer),
                            )
                        else:
                            # Only call task_done if you rely on queue.join()
                            for _ in range(len(buffer)):
                                self._raw_event_queue.task_done()
                        buffer.clear()

                except TimeoutError:
                    if buffer and self._flight_id is not None:
                        try:
                            await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        except Exception:
                            logger.exception(
                                "Raw event ingest worker (timeout flush): DB write failed — "
                                "batch of %d rows dropped",
                                len(buffer),
                            )
                        else:
                            for _ in range(len(buffer)):
                                self._raw_event_queue.task_done()
                        buffer.clear()
                except Exception:
                    logger.exception(
                        "Raw event ingest worker: unexpected error — batch of %d rows dropped",
                        len(buffer),
                    )
                    buffer.clear()

        except asyncio.CancelledError:
            # graceful exit: best effort flush
            if buffer and self._flight_id is not None:
                with suppress(Exception):
                    await self.repo.add_mavlink_events_many(self._flight_id, buffer)
            raise

    async def emergency_monitor_task(self):
        """Monitor for emergency conditions and handle them"""
        while self._running:
            try:
                # Only act if the drone explicitly flagged an emergency trigger.
                if getattr(self.drone, "dead_mans_switch_triggered", False):
                    if self.mqtt:
                        self.mqtt.publish(
                            "drone/emergency",
                            {
                                "type": "dead_mans_switch_triggered",
                                "message": "Connection lost - drone executing emergency protocol",
                                "timestamp": time.time(),
                            },
                            qos=2,
                        )  # QoS 2 for critical emergency messages

                    # Stop all other operations
                    self._running = False
                    # Reset to avoid repeated notifications
                    with suppress(Exception):
                        self.drone.dead_mans_switch_triggered = False
                    break
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.info(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)

    async def _run_preflight_checks(
        self,
        waypoints: list[Coordinate],
        alt: float,
        *,
        raise_on_fail: bool = True,
        mission_data: dict | None = None,
        **kwargs,
    ):

        mission_data = mission_data or {
            "type": "route",
            "waypoints": [
                {"lat": w.lat, "lon": w.lon, "alt": getattr(w, "alt", None) or alt}
                for w in waypoints
            ],
            "speed": kwargs.pop("mission_speed", settings.cruise_speed_mps),
            "altitude_agl": alt,
        }

        from backend.modules.warehouse.service.warehouse_preflight import (
            run_warehouse_ros_preflight_report,
            uses_warehouse_ros_preflight,
        )

        mission_type = str(mission_data.get("type") or "").lower()
        if uses_warehouse_ros_preflight(mission_type):
            report = await run_warehouse_ros_preflight_report(
                mission_data,
                cruise_alt=alt,
                flight_id=str(self._flight_id) if self._flight_id is not None else None,
                preflight_config=kwargs.pop("preflight_config", {}),
                mission_speed=kwargs.pop("mission_speed", settings.cruise_speed_mps),
                **kwargs,
            )
        else:
            vehicle_state = await asyncio.to_thread(self.drone.get_telemetry)
            orchestrator = PreflightOrchestrator(config=kwargs.pop("preflight_config", {}))
            config_overrides = dict(kwargs.pop("config_overrides", {}) or {})
            runtime_preflight = {
                "ENFORCE_PREFLIGHT_RANGE": settings.enforce_preflight_range,
                "HDOP_MAX": settings.HDOP_MAX,
                "SAT_MIN": settings.SAT_MIN,
                "HOME_MAX_DIST": settings.HOME_MAX_DIST,
                "GPS_FIX_TYPE_MIN": settings.GPS_FIX_TYPE_MIN,
                "EKF_THRESHOLD": settings.EKF_THRESHOLD,
                "COMPASS_HEALTH_REQUIRED": settings.COMPASS_HEALTH_REQUIRED,
                "BATTERY_MIN_V": settings.BATTERY_MIN_V,
                "BATTERY_MIN_PERCENT": settings.BATTERY_MIN_PERCENT,
                # Legacy aliases still used by some checks.
                "BATTERY_RESERVE_PCT": settings.BATTERY_MIN_PERCENT,
                "HEARTBEAT_MAX_AGE": settings.HEARTBEAT_MAX_AGE,
                "MSG_RATE_MIN_HZ": settings.MSG_RATE_MIN_HZ,
                "RTL_MIN_ALT": settings.RTL_MIN_ALT,
                "MIN_CLEARANCE": settings.MIN_CLEARANCE,
                "MIN_CLEARANCE_M": settings.MIN_CLEARANCE,
                "AGL_MIN": settings.AGL_MIN,
                "AGL_MAX": settings.AGL_MAX,
                "MAX_RANGE_M": settings.MAX_RANGE_M,
                "MAX_WAYPOINTS": settings.MAX_WAYPOINTS,
                "NFZ_BUFFER_M": settings.NFZ_BUFFER_M,
                "A_LAT_MAX": settings.A_LAT_MAX,
                "BANK_MAX_DEG": settings.BANK_MAX_DEG,
                "TURN_PENALTY_S": settings.TURN_PENALTY_S,
                "WP_RADIUS_M": settings.WP_RADIUS_M,
            }
            for key, value in runtime_preflight.items():
                config_overrides.setdefault(key, value)

            report = await orchestrator.run(
                vehicle_state,
                mission_data,
                flight_id=str(self._flight_id),
                allowed_modes=["STANDBY", "GUIDED", "AUTO", "LOITER"],
                config_overrides=config_overrides,
                **kwargs,
            )

        # --- log every individual result ---
        logger.info(
            f"Preflight overall: {report.overall_status} | "
            f"pass={report.summary.get('passed', 0)} "
            f"warn={report.summary.get('warned', 0)} "
            f"fail={report.summary.get('failed', 0)}"
        )
        for result in report.base_checks + report.mission_checks:
            level = (
                logging.WARNING
                if result.status == CheckStatus.WARN
                else logging.ERROR
                if result.status == CheckStatus.FAIL
                else logging.DEBUG
            )
            logger.log(level, f"  [{result.status}] {result.name}: {result.message or ''}")

        # --- publish report to MQTT so the ground station sees it ---
        if self.mqtt:
            self.mqtt.publish(
                "drone/preflight",
                {
                    "timestamp": time.time(),
                    "overall": report.overall_status,
                    "summary": report.summary,
                    "critical_failures": (
                        [{"name": c.name, "message": c.message} for c in report.critical_failures]
                        if report.critical_failures
                        else []
                    ),
                },
                qos=1,
            )

        # --- persist to DB ---
        if self._flight_id is not None:
            await self.record_flight_event(
                "preflight_report",
                {
                    "overall": report.overall_status,
                    "summary": report.summary,
                    "critical_failures": (
                        [c.name for c in report.critical_failures]
                        if report.critical_failures
                        else []
                    ),
                },
                flight_id=self._flight_id,
                source="orchestrator.preflight",
                category="preflight",
            )

        # --- abort on hard failure ---
        if report.overall_status == CheckStatus.FAIL:
            failed_names = (
                [c.name for c in report.critical_failures]
                if report.critical_failures
                else [
                    r.name
                    for r in report.base_checks + report.mission_checks
                    if r.status == CheckStatus.FAIL
                ]
            )
            if raise_on_fail:
                raise RuntimeError(
                    f"Preflight FAILED - mission aborted. Failed checks: {', '.join(failed_names)}"
                )

        # WARN is non-fatal: mission continues but operator has been notified
        if report.overall_status == CheckStatus.WARN:
            logger.warning("Preflight passed with warnings - proceeding with caution")

        return report

    async def _cleanup(self):
        """Clean up orchestrator resources"""
        try:
            self.drone.stop_dead_mans_switch()
        except Exception as e:
            logger.warning(f"Failed to stop dead man's switch: {e}")

        if self.video:
            try:
                self.video.close()
            except Exception as e:
                logger.warning(f"Failed to close video stream: {e}")

        try:
            self.drone.close()
        except Exception as e:
            logger.warning(f"Failed to close drone connection: {e}")
