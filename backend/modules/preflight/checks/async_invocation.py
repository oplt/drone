from __future__ import annotations

import asyncio
import inspect
from typing import Any


async def call_maybe_async(fn: Any, *args: Any) -> Any:
    """Call async providers directly and offload synchronous providers."""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args)
    result = await asyncio.to_thread(fn, *args)
    if inspect.isawaitable(result):
        return await result
    return result
