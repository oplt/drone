from __future__ import annotations

from backend.modules.patrol.event_trigger_config_service import (
    build_event_trigger_integration_info,
    patrol_mqtt_subscribe_pattern,
    patrol_mqtt_topic,
)


def test_patrol_mqtt_topic_org_scoped() -> None:
    assert patrol_mqtt_topic(org_id=42, owner_id=7) == "patrol/event-triggers/org/42"


def test_patrol_mqtt_topic_user_scoped() -> None:
    assert patrol_mqtt_topic(org_id=None, owner_id=7) == "patrol/event-triggers/user/7"


def test_patrol_mqtt_subscribe_pattern() -> None:
    assert patrol_mqtt_subscribe_pattern() == "patrol/event-triggers/#"


def test_build_event_trigger_integration_info_includes_mqtt() -> None:
    integration = build_event_trigger_integration_info(
        base_url="http://localhost:8000",
        org_id=5,
        owner_id=9,
        mqtt_broker="mqtt.example.com",
        mqtt_port=8883,
        mqtt_use_tls=True,
    )
    assert integration.webhook_url.endswith("/api/patrol/sensor-triggers")
    assert integration.mqtt is not None
    assert integration.mqtt.broker == "mqtt.example.com"
    assert integration.mqtt.port == 8883
    assert integration.mqtt.use_tls is True
    assert integration.mqtt.topic == "patrol/event-triggers/org/5"
