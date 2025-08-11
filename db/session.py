from __future__ import annotations
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings
from .models import Base

engine = create_async_engine(settings.database_url, pool_pre_ping=True,)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Optional index for spatial-ish queries (simple btree on lat/lon):
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_telemetry_lat_lon ON telemetry (lat, lon)")

async def close_db() -> None:
    await engine.dispose()
