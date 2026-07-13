from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import suppress
from uuid import uuid4

from pydantic import ValidationError

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.infrastructure.cache.redis import get_redis_client
from backend.infrastructure.messaging.mqtt_subscriber import MqttSubscriber, decode_json_payload
from backend.modules.identity.models import User
from backend.modules.organizations.models import Organization
from backend.modules.patrol.event_trigger_config_service import patrol_mqtt_subscribe_pattern
from backend.modules.patrol.sensor_config_schemas import PatrolSensorTriggerIn
from backend.modules.patrol.trigger_dispatch import dispatch_sensor_trigger

logger = logging.getLogger(__name__)


async def resolve_user_for_mqtt_topic(db, topic: str) -> User | None:
    parts = [part for part in str(topic).split("/") if part]
    if len(parts) < 4:
        return None
    if parts[0] != "patrol" or parts[1] != "event-triggers":
        return None

    scope, tenant_id_raw = parts[2], parts[3]
    try:
        tenant_id = int(tenant_id_raw)
    except ValueError:
        return None

    if scope == "org":
        org = await db.get(Organization, tenant_id)
        if org is None or org.owner_id is None:
            return None
        return await db.get(User, org.owner_id)

    if scope == "user":
        return await db.get(User, tenant_id)

    return None


class PatrolEventTriggerMqttService:
    _LEASE_KEY = "leader:patrol:event-trigger-mqtt"
    _LEASE_TTL_S = 30

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscriber: MqttSubscriber | None = None
        self._lease_token: str | None = None
        self._lease_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._subscriber is not None:
            return
        lease_token = uuid4().hex
        try:
            acquired = await get_redis_client().set(
                self._LEASE_KEY,
                lease_token,
                ex=self._LEASE_TTL_S,
                nx=True,
            )
        except Exception:
            logger.warning("Patrol MQTT leader lease unavailable; subscriber not started")
            return
        if not acquired:
            logger.info("Patrol MQTT subscriber owned by another API replica")
            return
        self._lease_token = lease_token
        self._loop = asyncio.get_running_loop()
        topic = patrol_mqtt_subscribe_pattern()
        client_id = f"patrol-event-triggers-{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"

        try:
            subscriber = MqttSubscriber(
                host=settings.mqtt_broker,
                port=int(settings.mqtt_port),
                username=settings.mqtt_user or "",
                password=settings.mqtt_pass or "",
                use_tls=bool(settings.mqtt_use_tls),
                ca_certs=settings.mqtt_ca_certs or None,
                client_id=client_id,
                topics=[(topic, 1)],
                on_message=self._handle_message_sync,
            )
        except Exception as exc:
            logger.warning(
                "Patrol event-trigger MQTT subscriber unavailable (%s:%s): %s",
                settings.mqtt_broker,
                settings.mqtt_port,
                exc,
            )
            await self._release_lease()
            return

        self._subscriber = subscriber
        self._lease_task = asyncio.create_task(self._renew_lease(), name="patrol-mqtt-lease")
        logger.info("Patrol event-trigger MQTT subscriber started on %s", topic)

    async def stop(self) -> None:
        try:
            if self._subscriber is not None:
                self._subscriber.close()
        finally:
            self._subscriber = None
            if self._lease_task is not None:
                self._lease_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._lease_task
                self._lease_task = None
            await self._release_lease()
            logger.info("Patrol event-trigger MQTT subscriber stopped")

    async def _renew_lease(self) -> None:
        while self._subscriber is not None and self._lease_token is not None:
            await asyncio.sleep(self._LEASE_TTL_S / 3)
            try:
                redis = get_redis_client()
                renewed = await redis.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] "
                    "then return redis.call('expire', KEYS[1], ARGV[2]) "
                    "else return 0 end",
                    1,
                    self._LEASE_KEY,
                    self._lease_token,
                    self._LEASE_TTL_S,
                )
                if not renewed:
                    logger.warning("Patrol MQTT leader lease lost; stopping subscriber")
                    subscriber, self._subscriber = self._subscriber, None
                    if subscriber is not None:
                        subscriber.close()
                    await self._release_lease()
                    return
                await redis.expire(self._LEASE_KEY, self._LEASE_TTL_S)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Patrol MQTT leader lease renewal failed", exc_info=True)

    async def _release_lease(self) -> None:
        token, self._lease_token = self._lease_token, None
        if token is None:
            return
        try:
            redis = get_redis_client()
            await redis.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] "
                "then return redis.call('del', KEYS[1]) "
                "else return 0 end",
                1,
                self._LEASE_KEY,
                token,
            )
        except Exception:
            logger.debug("Patrol MQTT leader lease release failed", exc_info=True)

    def _handle_message_sync(self, topic: str, payload: bytes) -> None:
        if self._loop is None:
            logger.warning("Patrol MQTT message dropped; event loop not ready (topic=%s)", topic)
            return
        future = asyncio.run_coroutine_threadsafe(self._handle_message(topic, payload), self._loop)
        future.add_done_callback(self._log_dispatch_error)

    @staticmethod
    def _log_dispatch_error(future: asyncio.Future) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("Patrol event-trigger MQTT dispatch failed")

    async def _handle_message(self, topic: str, payload: bytes) -> None:
        try:
            raw = decode_json_payload(payload)
        except (UnicodeDecodeError, ValueError) as exc:
            logger.warning(
                "Patrol MQTT trigger ignored (invalid JSON) topic=%s error=%s",
                topic,
                exc,
            )
            return

        try:
            trigger = PatrolSensorTriggerIn.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Patrol MQTT trigger ignored (invalid payload) topic=%s error=%s",
                topic,
                exc,
            )
            return

        if not trigger.sensor_id:
            trigger = trigger.model_copy(update={"sensor_id": "mqtt"})

        async with Session() as db:
            user = await resolve_user_for_mqtt_topic(db, topic)
            if user is None:
                logger.warning("Patrol MQTT trigger ignored (unknown topic tenant) topic=%s", topic)
                return

            try:
                result = await dispatch_sensor_trigger(trigger, user=user, db=db)
            except Exception:
                logger.exception(
                    "Patrol MQTT trigger dispatch failed topic=%s trigger_id=%s",
                    topic,
                    trigger.trigger_id,
                )
                return

            logger.info(
                "Patrol MQTT trigger processed topic=%s trigger_id=%s accepted=%s message=%s",
                topic,
                trigger.trigger_id,
                result.accepted,
                result.message,
            )


patrol_event_trigger_mqtt = PatrolEventTriggerMqttService()
