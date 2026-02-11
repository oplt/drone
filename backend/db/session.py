from __future__ import annotations
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.config import settings
from .models import Base

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()


# Replace the get_db() function with:
async def get_db() -> AsyncSession:
    async with Session() as session:
        try:
            yield session
        finally:
            await session.close()
