from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
import cv2
from video.stream import RaspberryClient
from analysis.llm import LLMAnalyzer
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from db.repository import TelemetryRepository
from config import settings, VideoAnalysisConfig
from analysis.prefilter import FramePreFilter, PreFilterConfig



class VideoAnalysisManager:
    """
    Owns:
      - video health monitoring
      - video recording to disk + DB VideoRecording rows
      - LLM-based frame analysis and publishing (MQTT + OPC UA + DB events)
    """

    def __init__(
            self,
            video: Optional[RaspberryClient],
            analyzer: LLMAnalyzer,
            repo: TelemetryRepository,
            mqtt: MqttClient,
            opcua: DroneOpcUaServer,
            cfg: VideoAnalysisConfig,
            video_cfg: Optional[VideoAnalysisConfig] = None,
    ) -> None:
        self.video = video
        self.analyzer = analyzer
        self.repo = repo
        self.mqtt = mqtt
        self.opcua = opcua
        self.cfg = cfg

        self._running: bool = True
        self._flight_id: Optional[int] = None

        self._video_health_interval = 5.0
        self.video_cfg: VideoAnalysisConfig = video_cfg or VideoAnalysisConfig()
        self._recording_id: int | None = None
        self._video_writer = None
        self._recorded_frame_count = 0
        self._recording_path: Optional[str] = None

        pf_cfg = PreFilterConfig(
            delta_mean=self.video_cfg.prefilter_delta_mean,
            delta_std=self.video_cfg.prefilter_delta_std,
            delta_edge_density=self.video_cfg.prefilter_delta_edge_density,
        )
        self._prefilter = FramePreFilter(pf_cfg)

    # ---- coordination -------------------------------------------------------------

    def set_flight_id(self, flight_id: int) -> None:
        self._flight_id = flight_id

    def stop(self) -> None:
        self._running = False

    # ---- video health ------------------------------------------------------------

    async def video_health_monitor_task(self) -> None:
        """Monitor video stream health and publish status."""
        logging.info("Starting video health monitor task...")

        while self._running:
            try:
                if self.video:
                    status = self.video.get_connection_status()

                    self.mqtt.publish(
                        "drone/video/status",
                        {
                            "timestamp": datetime.now(timezone.utc).timestamp(),
                            "healthy": status["healthy"],
                            "frame_count": status["frame_count"],
                            "fps": status["fps"],
                            "resolution": status["resolution"],
                            "recording": status["recording"],
                            "recording_file": status["recording_file"],
                        },
                        qos=1,
                    )

                    await self.opcua.update_video_status(
                        healthy=status["healthy"],
                        fps=status["fps"],
                        recording=status["recording"],
                    )

                    if not status["healthy"]:
                        logging.warning("Video stream is unhealthy")
                        self.mqtt.publish(
                            "drone/warnings",
                            {
                                "type": "video_stream_unhealthy",
                                "message": "Video stream connection issues detected",
                                "timestamp": datetime.now(timezone.utc).timestamp(),
                            },
                            qos=1,
                        )

                await asyncio.sleep(self._video_health_interval)

            except Exception as e:
                logging.error(f"Error in video health monitor: {e}")
                await asyncio.sleep(1.0)

    # ---- recording helpers --------------------------------------------------------

    async def _start_video_recording(self) -> None:
        if self._video_writer is not None:
            return

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = settings.drone_video_save_path or "./recordings"
        os.makedirs(out_dir, exist_ok=True)
        file_path = os.path.join(out_dir, f"flight_{self._flight_id}_{ts}.mp4")

        width = settings.drone_video_width
        height = settings.drone_video_height
        fps = float(settings.drone_video_fps)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._video_writer = cv2.VideoWriter(file_path, fourcc, fps, (width, height))
        self._recording_path = file_path
        self._recorded_frame_count = 0

        if self.video:
            self.video.set_recording(True)

        self._recording_id = await self.repo.start_recording(
            flight_id=self._flight_id,
            file_path=file_path,
            codec="mp4v",
            width=width,
            height=height,
            fps=fps,
            note="autostart",
        )

    async def _stop_video_recording(self) -> None:
        if self._video_writer is None or self._recording_id is None:
            return

        self._video_writer.release()
        self._video_writer = None

        file_path = self._recording_path
        size_bytes = None
        if file_path and os.path.exists(file_path):
            size_bytes = os.path.getsize(file_path)

        await self.repo.finish_recording(
            self._recording_id,
            frame_count=self._recorded_frame_count,
            size_bytes=size_bytes,
        )

        if self.video:
            self.video.set_recording(False)

        self._recording_id = None
        self._recorded_frame_count = 0
        self._recording_path = None

    # ---- main vision pipeline -----------------------------------------------------

    async def vision_task(self):
        """Process video frames for object detection and analysis.

            NOTE: The MJPEG reading + cv2.imdecode in self.video.frames() is blocking,
            so we pull frames via run_in_executor() to keep the asyncio event loop responsive.
        """
        if not self.video:
            logging.info("No video client configured; vision task exiting.")
            return

        from datetime import datetime, timezone  # local import to avoid top-of-file changes

        cfg = self.video_cfg
        logging.info(
            f"Starting vision task (stride={cfg.frame_stride}, "
            f"min_conf={cfg.min_confidence})"
        )

        frame_idx = 0
        frame_meta_buffer: list[dict] = []

        # Start recording when the vision task starts
        if settings.drone_video_save_stream:
            await self._start_video_recording()

        # Prepare blocking frame generator and executor
        loop = asyncio.get_running_loop()
        frame_gen = self.video.frames()  # this generator is blocking

        async def _next_frame():
            """Get next frame from blocking generator in a worker thread."""
            return await loop.run_in_executor(None, lambda: next(frame_gen))

        try:
            while self._running:
                try:
                    # Get next frame without blocking the event loop
                    _, frame = await _next_frame()
                except StopIteration:
                    logging.info("Video stream ended (StopIteration from frames()).")
                    break

                # 0) Always write the frame to the recording if enabled
                if self._video_writer is not None:
                    self._video_writer.write(frame)
                    self._recorded_frame_count += 1

                frame_idx += 1
                if cfg.frame_stride > 1 and (frame_idx % cfg.frame_stride) != 0:
                    # We still record every frame, just don't run the LLM on all of them
                    await asyncio.sleep(0)  # yield to event loop
                    continue

                # 1.5) Cheap pre-filter before calling LLM
                if cfg.enable_prefilter and not self._prefilter.is_interesting(frame):
                    # Frame looks very similar to recent ones -> skip LLM
                    await asyncio.sleep(0)
                    continue

                # 2) Run LLM detection once
                dets = await self.analyzer.detect_objects(frame)

                # 3) Apply min_confidence and max_detections
                dets = [d for d in dets if d.confidence >= cfg.min_confidence]
                if cfg.max_detections_per_frame > 0:
                    dets = dets[: cfg.max_detections_per_frame]

                # 4) Build metadata row for this analyzed frame (optional)
                if self._recording_id is not None:
                    frame_meta_buffer.append(
                        {
                            "frame_index": self._recorded_frame_count,
                            "ts": datetime.now(timezone.utc),
                            "detection_summary": [d.__dict__ for d in dets],
                            # optionally: "telemetry_id": <id from latest telemetry row>,
                        }
                    )

                # 5) Flush frame metadata occasionally (bulk insert)
                if (
                        frame_meta_buffer
                        and self._recording_id is not None
                        and len(frame_meta_buffer) >= 20
                ):
                    await self.repo.add_video_frames_many(
                        self._recording_id,
                        frame_meta_buffer,
                    )
                    frame_meta_buffer.clear()

                # 6) Publish to MQTT
                payload = [d.__dict__ for d in dets]
                if cfg.publish_mqtt:
                    self.mqtt.publish(cfg.mqtt_detection_topic, payload, qos=0)

                # 7) Update OPC UA
                if cfg.publish_opcua:
                    await self.opcua.update_detections(json.dumps(payload))

                # 8) Log detection events to DB
                if cfg.log_events and dets and self._flight_id is not None:
                    logging.info(
                        f"Detected {len(dets)} objects in video frame "
                        f"(min_conf={cfg.min_confidence})"
                    )
                    await self.repo.add_event(
                        self._flight_id,
                        "object_detected",
                        {
                            "count": len(dets),
                            "objects": [d.__dict__ for d in dets],
                        },
                    )

                # Let other tasks run
                await asyncio.sleep(0)

        except RuntimeError as e:
            error_msg = f"Video processing error: {str(e)}"
            logging.error(error_msg)
            self.mqtt.publish(
                "drone/events",
                {
                    "level": "error",
                    "msg": error_msg,
                    "timestamp": time.time(),
                },
                qos=1,
            )
        except Exception as e:
            error_msg = f"Unexpected error in vision task: {str(e)}"
            logging.error(error_msg)
            self.mqtt.publish(
                "drone/events",
                {
                    "level": "error",
                    "msg": error_msg,
                    "timestamp": time.time(),
                },
                qos=1,
            )
        finally:
            # Flush any remaining frame metadata
            if frame_meta_buffer and self._recording_id is not None:
                await self.repo.add_video_frames_many(
                    self._recording_id,
                    frame_meta_buffer,
                )
                frame_meta_buffer.clear()

            await self._stop_video_recording()
