from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config.runtime import bootstrap
from backend.core.database.model_registry import register_models

register_models()


def _engine_kwargs(database_url: str) -> dict[str, Any]:
    """Return conservative SQLAlchemy async-engine options.

    Keep this small and portable: SQLite/aiosqlite does not accept all queue-pool
    parameters, while PostgreSQL/MySQL benefit from pre-ping and connection recycle.
    """
    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
    }
    try:
        url = make_url(database_url)
    except Exception:
        return kwargs

    if url.get_backend_name().startswith("postgresql") or url.get_backend_name().startswith("mysql"):
        kwargs.update(
            {
                "pool_recycle": 1800,
                "pool_timeout": 30,
            }
        )
    return kwargs


engine: AsyncEngine = create_async_engine(
    bootstrap.database_url,
    **_engine_kwargs(bootstrap.database_url),
)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Schema is managed exclusively by Alembic migrations."""


async def close_db() -> None:
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with Session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
