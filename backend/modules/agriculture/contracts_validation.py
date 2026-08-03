"""Runtime validators shared by API contract tests and export boundaries."""

from __future__ import annotations

import re
from typing import Any

from shapely.geometry import shape


_FRONTEND_FUNCTION_RE = re.compile(
    r"export async function\s+(?P<name>\w+)[^{]*\{(?P<body>.*?)(?=\nexport async function|\Z)",
    re.DOTALL,
)
_AGRICULTURE_STRING_RE = re.compile(r"[`\"]([^`\"]*?/agriculture[^`\"]*)[`\"]")
_METHOD_RE = re.compile(r"method:\s*[\"'](?P<method>GET|POST|PUT|PATCH|DELETE)")


def frontend_route_references(source: str) -> set[tuple[str, str, str]]:
    """Extract typed client route references for a contract parity check.

    Dynamic template expressions are intentionally normalized to `{param}`;
    route matching below compares static path segments and treats OpenAPI
    parameters as wildcards.
    """
    references: set[tuple[str, str, str]] = set()
    for function in _FRONTEND_FUNCTION_RE.finditer(source):
        body = function.group("body")
        method_match = _METHOD_RE.search(body)
        method = method_match.group("method").lower() if method_match else "get"
        for raw_path in _AGRICULTURE_STRING_RE.findall(body):
            path = raw_path.split("${query", 1)[0]
            path = re.sub(r"\$\{[^}]*\}", "{param}", path)
            path = path.split("?", 1)[0]
            references.add((function.group("name"), method, path))
    return references


def agriculture_route_matches(frontend_path: str, openapi_path: str) -> bool:
    frontend_parts = frontend_path.rstrip("/").split("/")
    openapi_parts = openapi_path.rstrip("/").split("/")
    if len(frontend_parts) != len(openapi_parts):
        return False
    return all(
        left == right or (left.startswith("{") and right.startswith("{"))
        for left, right in zip(frontend_parts, openapi_parts)
    )


def missing_frontend_routes(
    references: set[tuple[str, str, str]], openapi_paths: dict[str, Any]
) -> list[tuple[str, str, str]]:
    agriculture_paths = {
        path: methods
        for path, methods in openapi_paths.items()
        if path.startswith("/agriculture/")
    }
    missing = []
    for function, method, frontend_path in sorted(references):
        matched = any(
            agriculture_route_matches(frontend_path, path) and method in methods
            for path, methods in agriculture_paths.items()
        )
        if not matched:
            missing.append((function, method, frontend_path))
    return missing


def validate_geojson(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("type") == "FeatureCollection":
        for feature in value.get("features", []):
            validate_geojson(feature)
        return value
    if value.get("type") == "Feature":
        geometry = value.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError("GeoJSON feature must contain geometry")
        validate_geojson(geometry)
        return value
    if value.get("type") not in {"Point", "LineString", "Polygon", "MultiPolygon", "MultiLineString", "MultiPoint"}:
        raise ValueError("Unsupported GeoJSON geometry type")
    geometry = shape(value)
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("GeoJSON geometry must be non-empty and valid")
    return value


def validate_tile_bounds(*, z: int, x: int, y: int) -> None:
    if z < 0 or z > 24:
        raise ValueError("Tile zoom must be between 0 and 24")
    dimension = 2**z
    if x < 0 or y < 0 or x >= dimension or y >= dimension:
        raise ValueError("Tile coordinate is outside zoom bounds")


def validate_status_transition(current: str, target: str, allowed: dict[str, set[str]]) -> None:
    if target not in allowed.get(current, set()):
        raise ValueError(f"Invalid agriculture status transition: {current} -> {target}")


def validate_event_sequence(events: list[dict[str, Any]]) -> None:
    previous = 0
    for event in events:
        sequence = int(event.get("sequence", 0))
        if sequence <= previous:
            raise ValueError("Agriculture realtime event sequence must increase monotonically")
        previous = sequence
