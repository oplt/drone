"""Stable public API errors for dependency and internal failures."""

from __future__ import annotations

from typing import Any

from .handlers import ApiError


def public_error(
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> ApiError:
    """Build an error safe to return without exposing exception text."""
    return ApiError(
        status_code=status_code,
        code=code,
        message=message,
        details=details or {},
    )
