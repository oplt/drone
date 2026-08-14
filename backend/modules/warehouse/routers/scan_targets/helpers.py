"""Warehouse scan-target routes — shared helpers."""

from __future__ import annotations

from fastapi import Response


def _set_scan_target_cache_headers(response: Response, *, offset: int) -> None:
    response.headers["Cache-Control"] = (
        "private, max-age=10" if offset == 0 else "private, no-store"
    )
    response.headers["Vary"] = "Authorization"


__all__ = ["_set_scan_target_cache_headers"]
