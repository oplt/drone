from __future__ import annotations

from typing import Any

import orjson
from fastapi.responses import Response


def orjson_response(
    content: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> Response:
    """Serialize large GeoJSON/list payloads with orjson."""
    body = orjson.dumps(content, default=str)
    response_headers = {"content-type": "application/json; charset=utf-8"}
    if headers:
        response_headers.update(headers)
    return Response(content=body, status_code=status_code, headers=response_headers)
