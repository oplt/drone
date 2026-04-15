from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import bootstrap

engine = create_async_engine(
    bootstrap.database_url,
    pool_pre_ping=True,
)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """No-op: schema is managed exclusively by Alembic migrations.
    Run `alembic -c backend/alembic.ini upgrade head` before starting the app.
    """


async def close_db() -> None:
    await engine.dispose()


# Replace the get_db() function with:
async def get_db() -> AsyncSession:
    async with Session() as session:
        try:
            yield session
        finally:
            await session.close()
