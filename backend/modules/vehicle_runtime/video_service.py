from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.core.config.runtime import settings
from backend.core.events import (
    VideoHealthEnvelopeV1,
    VideoHealthPayloadV1,
    next_runtime_sequence,
    utc_now,
)

logger = logging.getLogger(__name__)


class RuntimeVideoServiceMixin:
    def _init_video(self) -> None:
        """Initialize the video stream from settings. Called after drone connects."""
        if not settings.drone_video_enabled:
            logger.info("Drone video streaming disabled in configuration")
            return
        try:
            from backend.modules.warehouse.service.video import (
                warehouse_video_blocked,
                warehouse_video_skip_reason,
            )

            if warehouse_video_blocked():
                logger.info(
                    "Skipping drone video init for warehouse Gazebo sim: %s",
                    warehouse_video_skip_reason(),
                )
                return
        except Exception:
            pass
        from backend.modules.warehouse.service.video import effective_drone_video_use_gazebo

        if effective_drone_video_use_gazebo():
            logger.info("Gazebo video mode enabled; stream will be handled by API on demand")
            return
        if self.video is not None:
            logger.debug("Video stream already initialized, skipping")
            return
        try:
            if self._video_factory is None:
                logger.warning("Video enabled but no video stream adapter is configured")
                return
            self.video = self._video_factory.create()
            logger.info("Drone video stream initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize drone video stream: %s", e)
            self.video = None

    async def video_health_monitor_task(self):
        """Monitor video stream health and publish status"""
        logger.info("Starting video health monitor task...")

        while self._running:
            try:
                if self.video:
                    # Get video connection status
                    status = dict(self.video.get_connection_status())
                    status.setdefault("stream_started", True)
                    status.setdefault("source", getattr(self.video, "source", None))
                    recording_full_path = getattr(self.video, "recording_full_path", None)
                    if callable(recording_full_path):
                        status.setdefault("recording_path", recording_full_path())
                    video_payload = VideoHealthPayloadV1.from_status(status)
                    video_envelope = VideoHealthEnvelopeV1(
                        mission_runtime_id=getattr(
                            self,
                            "current_client_flight_id",
                            None,
                        ),
                        db_flight_id=self._runtime_db_flight_id(),
                        sequence=next_runtime_sequence(
                            getattr(self, "current_client_flight_id", None),
                            "orchestrator.video",
                        ),
                        emitted_at=utc_now(),
                        source="orchestrator.video",
                        mission=self._mission_context(),
                        payload=video_payload,
                    )

                    # Publish video health status to MQTT
                    if self.mqtt:
                        self.mqtt.publish(
                            "drone/video/status",
                            video_payload.to_legacy_status_payload(
                                timestamp_s=video_envelope.emitted_at.timestamp(),
                            ),
                            qos=1,
                        )
                        self.mqtt.publish(
                            "drone/runtime/video_health",
                            video_envelope.model_dump_jsonable(),
                            qos=1,
                        )

                    # Log warnings if video is unhealthy
                    if not video_payload.healthy:
                        logging.warning("Video stream is unhealthy")
                        if self.mqtt:
                            self.mqtt.publish(
                                "drone/warnings",
                                {
                                    "type": "video_stream_unhealthy",
                                    "message": "Video stream connection issues detected",
                                    "timestamp": time.time(),
                                },
                                qos=1,
                            )

                await asyncio.sleep(self._video_health_interval)

            except Exception as e:
                logger.error(f"Error in video health monitor: {e}")
                await asyncio.sleep(1.0)

    async def video_frame_pump_task(self):
        """Drain frames so the configured recorder actually receives video data."""
        if self.video is None:
            return

        logger.info("Starting video frame pump task...")
        frame_iter = self.video.frames()
        while self._running:
            try:
                packet = await asyncio.to_thread(next, frame_iter, None)
            except Exception as e:
                logger.error(f"Error in video frame pump: {e}")
                break

            if packet is None:
                break

            await asyncio.sleep(0)

    async def _start_mission_recording(self, mission: Any) -> bool:
        if (
            settings.drone_video_use_gazebo
            and settings.drone_video_save_stream
            and getattr(mission, "mission_type", None) != "warehouse_scan"
        ):
            if self._shared_video is None:
                logger.warning(
                    "Shared recording requested but no shared video adapter is configured"
                )
                return False
            try:
                status = await self._shared_video.start_recording()
                active = bool(status.get("recording"))
                if active and self._flight_id is not None:
                    await self.record_flight_event(
                        "video_recording_started",
                        {
                            "source": "shared_runtime",
                            "recording_file": status.get("recording_file"),
                            "recording_path": status.get("recording_path"),
                        },
                        flight_id=self._flight_id,
                        source="orchestrator.video",
                        category="video",
                    )
                return active
            except Exception as exc:
                logger.error("Failed to start shared video recording: %s", exc)
                return False
        if self.video and getattr(self.video, "enable_recording", False):
            try:
                await asyncio.to_thread(self.video.start_recording)
            except Exception as exc:
                logger.error("Failed to start video recording: %s", exc)
        return False

    async def _stop_mission_recording(self, active: bool) -> None:
        if not active or self._shared_video is None:
            return
        try:
            status = await self._shared_video.stop_recording()
            if self._flight_id is not None:
                await self.record_flight_event(
                    "video_recording_stopped",
                    {
                        "source": "shared_runtime",
                        "recording_file": status.get("recording_file"),
                        "recording_path": status.get("recording_path"),
                    },
                    flight_id=self._flight_id,
                    source="orchestrator.video",
                    category="video",
                )
        except Exception as exc:
            logger.warning("Failed to stop shared video recording: %s", exc)
