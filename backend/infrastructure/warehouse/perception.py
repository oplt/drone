from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import httpx

from backend.core.config.runtime import settings
from backend.modules.warehouse.ports import (
    WarehouseExplorationSnapshot,
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
    WarehousePerceptionPort,
    WarehousePerceptionStatus,
    WarehouseReplayStartRequest,
)

logger = logging.getLogger(__name__)

_cached_port: WarehousePerceptionPort | None = None


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _format_http_error(exc: Exception, *, timeout_s: float) -> str:
    text = str(exc).strip()
    if text:
        return text
    name = type(exc).__name__
    if name in {"ReadTimeout", "ConnectTimeout", "PoolTimeout", "WriteTimeout"}:
        return f"{name}: warehouse ROS bridge did not respond within {timeout_s:.1f}s"
    return name


class DisabledWarehousePerceptionPort:
    def __init__(
        self,
        *,
        profile: str,
        bridge_url: str,
        websocket_url: str,
        capture_root: str,
    ) -> None:
        self.profile = profile
        self.bridge_url = bridge_url
        self.websocket_url = websocket_url
        self.capture_root = capture_root

    async def status(self, *, deep: bool = False) -> WarehousePerceptionStatus:
        del deep
        return WarehousePerceptionStatus(
            configured=False,
            reachable=False,
            ready=False,
            status="disabled",
            profile=self.profile,
            bridge_url=self.bridge_url or None,
            websocket_url=self.websocket_url or None,
            capture_root=self.capture_root,
            detail="WAREHOUSE_ROS_BRIDGE_URL is not configured",
        )

    async def exploration_snapshot(self) -> WarehouseExplorationSnapshot:
        return WarehouseExplorationSnapshot()

    async def start_mapping(
        self, request: WarehouseMappingStartRequest
    ) -> WarehousePerceptionCommandResult:
        del request
        return self._disabled_result()

    async def stop_mapping(self, *, flight_id: str) -> WarehousePerceptionCommandResult:
        del flight_id
        return self._disabled_result()

    async def download_artifacts(self, *, flight_id: str, destination_dir: Path) -> list[str]:
        del flight_id, destination_dir
        return []

    async def start_replay(
        self, request: WarehouseReplayStartRequest
    ) -> WarehousePerceptionCommandResult:
        del request
        return self._disabled_result()

    async def stop_replay(self, *, replay_id: str) -> WarehousePerceptionCommandResult:
        del replay_id
        return self._disabled_result()

    @staticmethod
    def _disabled_result() -> WarehousePerceptionCommandResult:
        return WarehousePerceptionCommandResult(
            accepted=False,
            status="disabled",
            detail="Warehouse ROS bridge is not configured",
        )


class HttpWarehousePerceptionPort:
    def __init__(
        self,
        *,
        bridge_url: str,
        websocket_url: str,
        capture_root: str,
        profile: str,
        timeout_s: float,
        deep_timeout_s: float,
    ) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.websocket_url = websocket_url.strip()
        self.capture_root = capture_root
        self.profile = profile
        self.timeout_s = timeout_s
        self.deep_timeout_s = deep_timeout_s
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(deep_timeout_s, connect=min(2.0, timeout_s)),
            limits=limits,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def status(
        self,
        *,
        deep: bool = False,
        force: bool = False,
    ) -> WarehousePerceptionStatus:
        timeout_s = self.deep_timeout_s if deep else self.timeout_s
        if deep and force:
            path = "/health?deep=1&force=1"
        elif deep:
            path = "/health?deep=1"
        else:
            path = "/health"
        try:
            payload = await self._get_json(path, timeout_s=timeout_s)
        except Exception as exc:
            detail = _format_http_error(exc, timeout_s=timeout_s)
            logger.warning(
                "Warehouse ROS bridge health check failed bridge_url=%s deep=%s error=%s",
                self.bridge_url,
                deep,
                detail,
                extra={"bridge_url": self.bridge_url, "deep": deep, "error": detail},
            )
            return WarehousePerceptionStatus(
                configured=True,
                reachable=False,
                ready=False,
                status="unreachable",
                profile=self.profile,
                bridge_url=self.bridge_url,
                websocket_url=self.websocket_url or None,
                capture_root=self.capture_root,
                detail=detail,
            )

        components = _as_dict(payload.get("components"))
        for bridge_field in (
            "diagnostics_ready",
            "probe_in_progress",
            "cache_ready",
            "probe_mode",
            "from_cache",
            "health_sample_timestamp",
            "capabilities",
        ):
            if bridge_field not in components and bridge_field in payload:
                components[bridge_field] = payload.get(bridge_field)
        if "capabilities" in payload and "capabilities" not in components:
            components["capabilities"] = payload.get("capabilities")
        ready = bool(payload.get("ready", payload.get("healthy", False)))
        status = _string(payload.get("status")) or ("ready" if ready else "degraded")
        if not ready:
            logger.warning(
                (
                    "Warehouse ROS bridge reports degraded health status=%s topic_count=%s "
                    "missing_required=%s missing_nvblox=%s probe_error=%s"
                ),
                status,
                components.get("ros_topic_count"),
                components.get("missing_required_topics"),
                components.get("missing_nvblox_topics"),
                components.get("ros_topic_probe_error"),
                extra={
                    "bridge_url": self.bridge_url,
                    "status": status,
                    "ros_topic_count": components.get("ros_topic_count"),
                    "missing_required_topics": components.get("missing_required_topics"),
                    "missing_nvblox_topics": components.get("missing_nvblox_topics"),
                    "probe_error": components.get("ros_topic_probe_error"),
                },
            )
        return WarehousePerceptionStatus(
            configured=True,
            reachable=True,
            ready=ready,
            status=status,
            profile=_string(payload.get("profile")) or self.profile,
            bridge_url=self.bridge_url,
            websocket_url=_string(payload.get("websocket_url")) or self.websocket_url or None,
            capture_root=_string(payload.get("capture_root")) or self.capture_root,
            detail=_string(payload.get("detail")),
            components=components,
        )

    async def exploration_snapshot(self) -> WarehouseExplorationSnapshot:
        try:
            payload = await self._get_json("/exploration/snapshot", timeout_s=self.timeout_s)
        except Exception as exc:
            logger.warning(
                "Warehouse ROS bridge exploration snapshot failed bridge_url=%s error=%s",
                self.bridge_url,
                _format_http_error(exc, timeout_s=self.timeout_s),
                extra={"bridge_url": self.bridge_url},
            )
            return WarehouseExplorationSnapshot()
        return WarehouseExplorationSnapshot.model_validate(payload)

    async def start_mapping(
        self, request: WarehouseMappingStartRequest
    ) -> WarehousePerceptionCommandResult:
        payload = request.model_dump(mode="json")
        if not payload.get("profile"):
            payload["profile"] = self.profile
        if not payload.get("capture_root"):
            payload["capture_root"] = self.capture_root
        logger.info(
            "Starting warehouse ROS mapping via bridge flight_id=%s map_id=%s profile=%s",
            payload.get("flight_id"),
            payload.get("warehouse_map_id"),
            payload.get("profile"),
            extra={
                "bridge_url": self.bridge_url,
                "flight_id": payload.get("flight_id"),
                "warehouse_map_id": payload.get("warehouse_map_id"),
                "profile": payload.get("profile"),
            },
        )
        result = self._command_result(await self._post_json("/mapping/start", payload))
        logger.info(
            "Warehouse ROS mapping start result flight_id=%s accepted=%s status=%s detail=%s",
            payload.get("flight_id"),
            result.accepted,
            result.status,
            result.detail,
            extra={
                "flight_id": payload.get("flight_id"),
                "accepted": result.accepted,
                "status": result.status,
                "detail": result.detail,
            },
        )
        return result

    async def stop_mapping(self, *, flight_id: str) -> WarehousePerceptionCommandResult:
        logger.info(
            "Stopping warehouse ROS mapping via bridge flight_id=%s",
            flight_id,
            extra={"bridge_url": self.bridge_url, "flight_id": flight_id},
        )
        result = self._command_result(
            await self._post_json("/mapping/stop", {"flight_id": flight_id})
        )
        logger.info(
            "Warehouse ROS mapping stop result flight_id=%s accepted=%s status=%s",
            flight_id,
            result.accepted,
            result.status,
            extra={"flight_id": flight_id, "accepted": result.accepted, "status": result.status},
        )
        return result

    async def download_artifacts(self, *, flight_id: str, destination_dir: Path) -> list[str]:
        payload = await self._post_json(
            "/mapping/artifacts/download",
            {"flight_id": flight_id, "destination_dir": str(destination_dir)},
        )
        paths = payload.get("paths", [])
        if not isinstance(paths, list):
            return []
        return [str(path) for path in paths]

    async def start_replay(
        self, request: WarehouseReplayStartRequest
    ) -> WarehousePerceptionCommandResult:
        payload = request.model_dump(mode="json")
        payload.setdefault("profile", self.profile)
        return self._command_result(await self._post_json("/replay/start", payload))

    async def stop_replay(self, *, replay_id: str) -> WarehousePerceptionCommandResult:
        return self._command_result(await self._post_json("/replay/stop", {"replay_id": replay_id}))

    async def _get_json(self, path: str, *, timeout_s: float | None = None) -> dict[str, Any]:
        effective_timeout = self.timeout_s if timeout_s is None else timeout_s
        timeout = httpx.Timeout(effective_timeout, connect=min(2.0, effective_timeout))
        response = await self._client.get(f"{self.bridge_url}{path}", timeout=timeout)
        logger.debug(
            "Warehouse ROS bridge GET",
            extra={"url": f"{self.bridge_url}{path}", "status_code": response.status_code},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def _post_json(
            self,
            path: str,
            payload: dict[str, object],
            *,
            timeout_s: float | None = None,
    ) -> dict[str, Any]:
        effective_timeout = self.deep_timeout_s if timeout_s is None else timeout_s
        timeout = httpx.Timeout(effective_timeout, connect=min(2.0, effective_timeout))
        url = f"{self.bridge_url}{path}"
        try:
            response = await self._client.post(url, json=payload, timeout=timeout)
            logger.info(
                "Warehouse ROS bridge POST url=%s status_code=%s",
                url,
                response.status_code,
                extra={"url": url, "status_code": response.status_code},
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except Exception as exc:
            detail = _format_http_error(exc, timeout_s=effective_timeout)
            logger.warning(
                "Warehouse ROS bridge POST failed url=%s error=%s",
                url,
                detail,
                extra={"url": url, "error": detail},
            )
            return {
                "accepted": False,
                "status": "unreachable",
                "detail": detail,
                "data": {},
                "paths": [],
            }

    @staticmethod
    def _command_result(payload: dict[str, Any]) -> WarehousePerceptionCommandResult:
        data = _as_dict(payload.get("data"))
        accepted_raw = payload.get("accepted", True)
        accepted = (
            accepted_raw
            if isinstance(accepted_raw, bool)
            else str(accepted_raw).strip().lower() not in {"0", "false", "no", "off"}
        )
        return WarehousePerceptionCommandResult(
            accepted=accepted,
            status=_string(payload.get("status")) or ("accepted" if accepted else "failed"),
            detail=_string(payload.get("detail")),
            data=data,
        )


def build_warehouse_perception_port() -> WarehousePerceptionPort:
    global _cached_port
    if _cached_port is not None:
        return _cached_port
    bridge_url = settings.WAREHOUSE_ROS_BRIDGE_URL.strip()
    websocket_url = settings.WAREHOUSE_ROS_WS_URL.strip()
    capture_root = settings.WAREHOUSE_ROS_CAPTURE_ROOT.strip()
    profile = settings.WAREHOUSE_ROS_PROFILE.strip() or "isaac_ros_nvblox_stereo"
    timeout_s = max(0.1, float(settings.WAREHOUSE_ROS_BRIDGE_TIMEOUT_S))
    deep_timeout_s = max(timeout_s, float(settings.WAREHOUSE_ROS_BRIDGE_DEEP_TIMEOUT_S))
    if not bridge_url:
        _cached_port = DisabledWarehousePerceptionPort(
            profile=profile,
            bridge_url=bridge_url,
            websocket_url=websocket_url,
            capture_root=capture_root,
        )
        return _cached_port
    _cached_port = HttpWarehousePerceptionPort(
        bridge_url=bridge_url,
        websocket_url=websocket_url,
        capture_root=capture_root,
        profile=profile,
        timeout_s=timeout_s,
        deep_timeout_s=deep_timeout_s,
    )
    return _cached_port


def reset_warehouse_perception_port_for_tests() -> None:
    global _cached_port
    _cached_port = None
