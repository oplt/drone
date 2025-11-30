from __future__ import annotations
import asyncio
import logging
from typing import Optional
from messaging.mqtt import MqttClient
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher
from db.repository import TelemetryRepository, TelemetryBuffer


class TelemetryManager:
    """
    Owns telemetry publisher lifecycle and MQTT -> DB ingestion of MAVLink events.
    """

    def __init__(
            self,
            mqtt: MqttClient,
            publisher: ArduPilotTelemetryPublisher,
            repo: TelemetryRepository,
    ) -> None:
        self.mqtt = mqtt
        self.publisher = publisher
        self.repo = repo

        self._running: bool = True
        self._flight_id: Optional[int] = None
        self._raw_event_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=2000)
        self._telemetry_buffer: TelemetryBuffer | None = None

    # ---- coordination -------------------------------------------------------------

    def set_flight_id(self, flight_id: int) -> None:
        self._flight_id = flight_id

    @property
    def flight_id(self) -> Optional[int]:
        return self._flight_id

    @property
    def raw_event_queue(self) -> asyncio.Queue[dict]:
        return self._raw_event_queue

    def stop(self) -> None:
        self._running = False

    async def _telemetry_ingest_worker(self):
        """
            Drain MQTT-parsed telemetry rows and batch-insert into TelemetryRecord
            using TelemetryBuffer (size + time–based flushing).
        """

        # Wait until flight_id is available
        while self._flight_id is None:
            logging.info("Telemetry worker waiting for flight_id...")
            await asyncio.sleep(0.5)

        # Initialize buffer for this flight
        self._telemetry_buffer = TelemetryBuffer(
            repo=self.repo,
            flight_id=self._flight_id,
            batch_size=50,         # tune: how many rows per batch
            max_interval_sec=1.0,  # tune: max seconds between commits
        )
        logging.info("Telemetry buffer initialized for flight %s", self._flight_id)

        try:
            while self._running:
                try:
                    row = await self._ingest_queue.get()
                except asyncio.CancelledError:
                    break

                try:
                    # TelemetryBuffer decides when to actually flush to DB
                    await self._telemetry_buffer.add(row)
                except Exception as e:
                    logging.error(f"Error adding telemetry row to buffer: {e}")

                # Mark item as processed even on error, to avoid blocking queue
                self._ingest_queue.task_done()

        except Exception as e:
            logging.error(f"Error in _telemetry_ingest_worker: {e}")
        finally:
            # Final flush on shutdown
            if self._telemetry_buffer is not None:
                try:
                    await self._telemetry_buffer.flush()
                except Exception as e:
                    logging.error(f"Error flushing telemetry buffer on shutdown: {e}")


    # ---- telemetry publisher ------------------------------------------------------

    async def telemetry_publish_task(self) -> None:
        """Manage the telemetry publisher lifecycle."""
        try:
            if not await asyncio.to_thread(self.publisher.start):
                logging.error("Failed to start telemetry publisher")
                return

            while self._running and self.publisher.is_alive():
                await asyncio.sleep(1.0)
        except Exception as e:
            logging.error(f"Telemetry publisher error: {e}")
        finally:
            if self.publisher.is_running:
                await asyncio.to_thread(self.publisher.stop)

    # ---- MQTT ingest -> raw MAVLink events ---------------------------------------

    async def _raw_event_ingest_worker(self) -> None:
        """Drain raw MAVLink events from MQTT and bulk-insert into MavlinkEvent."""
        BATCH_SIZE = 200
        INTERVAL_S = 0.1
        buffer: list[dict] = []
        logging.info("Starting _raw_event_ingest_worker")

        while True:  # task is cancelled by Orchestrator
            try:
                item = await asyncio.wait_for(self._raw_event_queue.get(), timeout=INTERVAL_S)
                logging.debug(f"Received item from queue: {item.get('msg_type', 'UNKNOWN')}")
                buffer.append(item)

                for _ in range(BATCH_SIZE - 1):
                    try:
                        buffer.append(self._raw_event_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                if buffer:
                    if self._flight_id is None:
                        logging.warning(
                            "Flight ID is None, cannot save MavlinkEvent data"
                        )
                        buffer.clear()
                        continue

                    logging.info(
                        f"Processing batch of {len(buffer)} events for flight {self._flight_id}"
                    )
                    try:
                        inserted_count = await self.repo.add_mavlink_events_many(
                            self._flight_id,
                            buffer,
                        )
                        logging.info(
                            f"Inserted {inserted_count} MavlinkEvent records"
                        )
                    except Exception as e:
                        logging.error(
                            f"Failed to insert MavlinkEvent data: {e}"
                        )

                    for _ in buffer:
                        self._raw_event_queue.task_done()
                    buffer.clear()
            except asyncio.TimeoutError:
                if buffer:
                    if self._flight_id is None:
                        logging.warning(
                            "Flight ID is None, cannot save MavlinkEvent data"
                        )
                        buffer.clear()
                        continue

                    logging.info(
                        f"Timeout flush: processing {len(buffer)} events for flight {self._flight_id}"
                    )
                    try:
                        inserted_count = await self.repo.add_mavlink_events_many(
                            self._flight_id,
                            buffer,
                        )
                        logging.info(
                            f"Inserted {inserted_count} MavlinkEvent records (timeout flush)"
                        )
                    except Exception as e:
                        logging.error(
                            f"Failed to insert MavlinkEvent data (timeout flush): {e}"
                        )

                    for _ in buffer:
                        self._raw_event_queue.task_done()
                    buffer.clear()
            except Exception as e:
                logging.error(f"Error in _raw_event_ingest_worker: {e}")
                buffer.clear()

    async def mqtt_subscriber_task(self) -> None:
        """Listen for MQTT messages and enqueue raw events."""
        try:
            while self._flight_id is None:
                logging.info(
                    "Waiting for flight_id to be set before starting MQTT subscriber..."
                )
                await asyncio.sleep(0.5)

            logging.info(
                f"Starting MQTT subscriber with flight_id: {self._flight_id}"
            )

            # Attach queues so mqtt client can enqueue telemetry rows and raw MAVLink events
            self.mqtt.attach_ingest_queue(self._ingest_queue)
            self.mqtt.attach_raw_event_queue(self._raw_event_queue)

            if not await asyncio.to_thread(
                    self.mqtt.subscribe_to_topics,
                    self._flight_id,
            ):
                logging.error("Failed to start MQTT subscriber")
                while self._running:
                    await asyncio.sleep(1.0)

            logging.info(
                "MQTT subscriber started and listening for messages"
            )
            while self._running:
                await asyncio.sleep(1.0)
        except Exception as e:
            logging.error(f"Mqtt broker subscribe error: {e}")
