"""Normalize exceptions for low-cardinality metric and audit labels."""

from __future__ import annotations

import asyncio

from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, TimeoutError as SATimeoutError


def normalize_error_type(exc: BaseException | None) -> str:
    if exc is None:
        return "unknown"
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "connection_error"
    if isinstance(exc, OperationalError):
        orig = getattr(exc, "orig", None)
        if orig is not None:
            name = type(orig).__name__.lower()
            if "deadlock" in name:
                return "deadlock"
            if "timeout" in name:
                return "timeout"
            if "connection" in name:
                return "connection_error"
        return "operational_error"
    if isinstance(exc, IntegrityError):
        return "integrity_error"
    if isinstance(exc, DBAPIError):
        return "dbapi_error"
    if isinstance(exc, ValueError):
        return "value_error"
    if isinstance(exc, RuntimeError):
        return "runtime_error"
    if isinstance(exc, PermissionError):
        return "permission_error"
    if isinstance(exc, FileNotFoundError):
        return "not_found"
    return type(exc).__name__
