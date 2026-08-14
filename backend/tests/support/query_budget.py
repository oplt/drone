from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine


@asynccontextmanager
async def assert_max_sql_queries(engine: AsyncEngine, max_queries: int):
    """Fail when an async SQLAlchemy code path exceeds a fixed query budget."""
    sync_engine = engine.sync_engine
    state = {"count": 0}

    def before_cursor_execute(*_args, **_kwargs) -> None:
        state["count"] += 1

    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield lambda: state["count"]
    finally:
        event.remove(sync_engine, "before_cursor_execute", before_cursor_execute)

    observed = state["count"]
    assert observed <= max_queries, (
        f"Expected at most {max_queries} SQL queries, observed {observed}"
    )
