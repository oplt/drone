from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from backend.core.config.runtime import settings
from backend.core.events import (
    TelemetryEnvelopeV1,
    TelemetryPayloadV1,
    utc_now,
)
from backend.core.events.mavlink import (
    TELEMETRY_MAVLINK_TYPES,
    process_mavlink_message,
    raw_event_from_mavlink_message,
)

logger = logging.getLogger(__name__)


class RuntimeTelemetryServiceMixin:
    async def start_live_telemetry(
        self,
        mavlink_connection_str: str | None = None,
    ) -> bool:
        if self._telemetry_stream_running:
            return False

        if self._event_loop is None:
            self.bind_event_loop(asyncio.get_running_loop())

        conn_str = mavlink_connection_str or self._telemetry_conn_str
        if not conn_str:
            raise RuntimeError("No MAVLink connection string provided for telemetry")

        self._telemetry_conn_str = conn_str
        self._telemetry_stream_running = True
        self._metrics["ingest_started_at"] = utc_now().isoformat()
        self.fanout.set_runtime_active(running=True, source_connected=False)
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_worker,
            args=(conn_str,),
            daemon=True,
            name="OrchestratorTelemetryWorker",
        )
        self._telemetry_thread.start()
        logger.info("Orchestrator live telemetry ingest started")
        return True

    async def stop_live_telemetry(self) -> bool:
        if not self._telemetry_stream_running:
            return False

        self._telemetry_stream_running = False
        thread = self._telemetry_thread
        if thread and thread.is_alive():
            await asyncio.to_thread(thread.join, 3.0)
        self._telemetry_thread = None
        self._telemetry_mav_conn = None
        self.fanout.set_runtime_active(running=False, source_connected=False)
        logger.info("Orchestrator live telemetry ingest stopped")
        return True

    def _telemetry_worker(self, conn_str: str) -> None:
        mav_conn = None
        message_buffer: list[dict[str, Any]] = []
        last_broadcast_time = time.monotonic()
        last_message_at = time.monotonic()
        last_heartbeat_check_at = time.monotonic()
        reconnect_attempt = 0
        reconnect_backoff_s = 2.0

        try:
            logger.info("Connecting orchestrator telemetry ingest to MAVLink: %s", conn_str)
            mav_conn = self._telemetry_connections.connect(conn_str)
            self._telemetry_mav_conn = mav_conn
            self.fanout.set_runtime_active(running=True, source_connected=True)

            heartbeat = mav_conn.wait_heartbeat(timeout=10)
            if not heartbeat:
                raise RuntimeError("MAVLink heartbeat timeout")
            last_message_at = time.monotonic()

            try:
                self._telemetry_connections.request_all_streams(mav_conn)
            except Exception as exc:
                logger.warning("Could not request MAVLink data streams: %s", exc)

            while self._telemetry_stream_running:
                try:
                    now_s = time.monotonic()
                    if now_s - last_heartbeat_check_at >= 5.0:
                        last_heartbeat_check_at = now_s
                        message_age_ms = int((now_s - last_message_at) * 1000)
                        if message_age_ms > 8000:
                            reconnect_attempt += 1
                            logger.warning(
                                "Telemetry MAVLink stale — reconnecting "
                                "last_message_age_ms=%s reconnect_attempt=%s connection_url=%s",
                                message_age_ms,
                                reconnect_attempt,
                                conn_str,
                            )
                            if mav_conn:
                                with suppress(Exception):
                                    mav_conn.close()
                            time.sleep(min(reconnect_backoff_s, 15.0))
                            reconnect_backoff_s = min(reconnect_backoff_s * 1.5, 15.0)
                            mav_conn = self._telemetry_connections.connect(conn_str)
                            self._telemetry_mav_conn = mav_conn
                            self.fanout.set_runtime_active(
                                running=True,
                                source_connected=True,
                            )
                            last_message_at = time.monotonic()
                        else:
                            reconnect_backoff_s = 2.0

                    msg = mav_conn.recv_match(
                        blocking=False,
                        timeout=0.05,
                        type=TELEMETRY_MAVLINK_TYPES,
                    )
                    if msg:
                        last_message_at = time.monotonic()
                        msg_dict = msg.to_dict()
                        emitted_s = time.time()
                        if self.mqtt:
                            raw_payload = dict(msg_dict)
                            raw_payload["timestamp"] = emitted_s
                            self.mqtt.publish(settings.telemetry_topic, raw_payload, qos=0)

                        if self._running and self._flight_id is not None:
                            self._enqueue_raw_event(
                                raw_event_from_mavlink_message(
                                    msg_dict,
                                    flight_id=self._flight_id,
                                    timestamp_s=emitted_s,
                                )
                            )

                        telemetry_delta = process_mavlink_message(
                            msg_dict,
                            current_snapshot=self._last_telemetry_snapshot,
                        )
                        if telemetry_delta:
                            snapshot = dict(self._last_telemetry_snapshot)
                            snapshot.update(telemetry_delta)
                            snapshot["timestamp"] = emitted_s
                            self._last_telemetry_snapshot = snapshot
                            message_buffer.append(telemetry_delta)

                    now_s = time.monotonic()
                    if (
                        now_s - last_broadcast_time >= self._telemetry_broadcast_interval
                        and message_buffer
                    ):
                        consolidated: dict[str, Any] = {}
                        for update in message_buffer:
                            consolidated.update(update)

                        emitted_s = float(self._last_telemetry_snapshot.get("timestamp") or now_s)
                        snapshot = dict(self._last_telemetry_snapshot)
                        snapshot.update(consolidated)
                        snapshot["timestamp"] = emitted_s
                        self._last_telemetry_snapshot = snapshot

                        envelope = TelemetryEnvelopeV1(
                            mission_runtime_id=self._current_mission_runtime_id(),
                            db_flight_id=self._runtime_db_flight_id(),
                            sequence=self._sequence("orchestrator.telemetry"),
                            emitted_at=datetime.fromtimestamp(emitted_s, tz=UTC),
                            source="orchestrator.telemetry",
                            mission=self._mission_context(),
                            payload=TelemetryPayloadV1.from_legacy_snapshot(
                                snapshot,
                                coalesced_message_count=len(message_buffer),
                            ),
                        )
                        self._schedule_coro(self._fanout_runtime_envelope(envelope))
                        message_buffer.clear()
                        last_broadcast_time = now_s

                    time.sleep(0.001)
                except Exception as exc:
                    if self._telemetry_stream_running:
                        logger.error("Telemetry ingest worker error: %s", exc)
                    time.sleep(0.1)
        except Exception as exc:
            logger.error("Orchestrator telemetry ingest failed: %s", exc)
        finally:
            if mav_conn is not None:
                with suppress(Exception):
                    mav_conn.close()
            self._telemetry_mav_conn = None
            self._telemetry_stream_running = False
            self.fanout.set_runtime_active(running=False, source_connected=False)
            logger.info("Orchestrator telemetry worker stopped")

    async def heartbeat_task(self):
        logger.info("Starting heartbeat task...")
        try:
            while self._running:
                if self.mqtt:
                    self.mqtt.publish(
                        "drone/heartbeat",
                        {"timestamp": time.time(), "status": "alive"},
                        qos=1,
                    )
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.warning(f"Heartbeat task error: {e}")
