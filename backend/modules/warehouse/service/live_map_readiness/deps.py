"""Warehouse live-map readiness — test monkeypatching helpers."""

from __future__ import annotations

import asyncio as _asyncio

from backend.infrastructure.warehouse.bridge_config import (
    list_ros2_topics as _default_list_ros2_topics,
    list_ros2_topics_async as _default_list_ros2_topics_async,
    ros_command_env as _default_ros_command_env,
)

asyncio = _asyncio
list_ros2_topics = _default_list_ros2_topics
list_ros2_topics_async = _default_list_ros2_topics_async
ros_command_env = _default_ros_command_env


def resolve(name: str):
    from backend.modules.warehouse.service import live_map_readiness as package

    return getattr(package, name)


async def list_topics_async(ws):
    from backend.modules.warehouse.service import live_map_readiness as package

    patched_sync = getattr(package, "list_ros2_topics", None)
    if patched_sync is not None and patched_sync is not _default_list_ros2_topics:
        result = patched_sync(ws)
        if _asyncio.iscoroutine(result):
            return set(await result)
        return set(result)
    async_fn = package.list_ros2_topics_async
    return set(await async_fn(ws))


__all__ = [
    "asyncio",
    "list_ros2_topics",
    "list_ros2_topics_async",
    "list_topics_async",
    "resolve",
    "ros_command_env",
]
