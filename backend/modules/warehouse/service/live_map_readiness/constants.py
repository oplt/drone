"""Warehouse live-map readiness — shared constants."""

from __future__ import annotations

from typing import Literal

TopicBridgeKind = Literal[
    "pointcloud2",
    "internal_layer",
    "missing",
    "wrong_type",
]

_MAX_TOPIC_INFO_WORKERS = 8
_MAX_MESSAGE_PROBE_CONCURRENCY = 4
_RGBD_READINESS_KEY = "warehouse:readiness:rgbd:v1"
_TOPIC_PROBE_KEY = "warehouse:readiness:topic-probe:v1"
