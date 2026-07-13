"""Shared pagination contracts for list endpoints."""

from __future__ import annotations

import base64
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")
MAX_PAGE_SIZE = 200


def clamp_page_limit(limit: int, *, default: int = 50, maximum: int = MAX_PAGE_SIZE) -> int:
    """Normalize externally supplied limits before they reach a repository."""
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def encode_offset_cursor(offset: int) -> str:
    if offset < 0:
        raise ValueError("offset must be non-negative")
    raw = f"v1:offset:{offset}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_offset_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        version, marker, raw_offset = value.split(":", 2)
        if version != "v1" or marker != "offset":
            raise ValueError
        offset = int(raw_offset)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Invalid pagination cursor") from exc
    if offset < 0:
        raise ValueError("Invalid pagination cursor")
    return offset


class PageMeta(BaseModel):
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=0)


class OffsetPage(BaseModel, Generic[T]):
    items: list[T]
    page: PageMeta


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    total: int | None = Field(default=None, ge=0)


class CursorPage(Page[T], Generic[T]):
    """Stable list contract for cursor/keyset endpoints."""


def page_from_offset(
    items: list[T],
    *,
    limit: int,
    offset: int,
    total: int | None = None,
) -> Page[T]:
    """Build a page from a ``limit + 1`` repository read."""
    page_limit = clamp_page_limit(limit)
    has_more = len(items) > page_limit
    visible = items[:page_limit]
    return Page(
        items=visible,
        next_cursor=encode_offset_cursor(offset + page_limit) if has_more else None,
        total=total,
    )
