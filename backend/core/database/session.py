from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config.runtime import bootstrap
from backend.core.database.model_registry import register_models

register_models()

engine = create_async_engine(
    bootstrap.database_url,
    pool_pre_ping=True,
)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Schema is managed exclusively by Alembic migrations."""


async def close_db() -> None:
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with Session() as session:
        yield session
