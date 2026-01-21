# db/session.py - FULL CORRECTED VERSION
from __future__ import annotations
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from sqlalchemy import text
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging
from config import settings
from .models import Base

# ==================== CONNECTION POOL CONFIGURATION ====================
def create_engine_with_pool():
    """Create SQLAlchemy engine with optimized connection pooling"""

    # Pool configuration
    pool_config = {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_pre_ping": settings.DB_POOL_PRE_PING,
        "poolclass": AsyncAdaptedQueuePool,
        "echo": settings.DB_ECHO,
        "future": True,
    }

    # For SQLite, use NullPool
    if "sqlite" in settings.database_url.lower():
        pool_config["poolclass"] = NullPool
        logging.info("Using NullPool for SQLite (no connection pooling)")

    engine = create_async_engine(
        settings.database_url,
        **pool_config
    )

    return engine


# Create engine with pooling
engine = create_engine_with_pool()

# Session factory
Session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=True,
)

# ==================== HEALTH CHECK FUNCTIONS ====================
async def check_pool_health() -> dict:
    """Check connection pool health and stats"""
    try:
        # Get raw connection to check pool
        async with engine.connect() as conn:
            # Execute a simple query to verify connection
            result = await conn.execute(text("SELECT 1 as health_check"))
            health = result.fetchone()  # NO AWAIT HERE - fetchone() is synchronous

            # Get pool stats (if available)
            pool = engine.pool
            # Call methods to get actual values, not method objects
            try:
                pool_size = pool.size() if hasattr(pool, 'size') and callable(getattr(pool, 'size', None)) else None
                checked_in = pool.checkedin() if hasattr(pool, 'checkedin') and callable(getattr(pool, 'checkedin', None)) else None
                checked_out = pool.checkedout() if hasattr(pool, 'checkedout') and callable(getattr(pool, 'checkedout', None)) else None
                overflow = pool.overflow() if hasattr(pool, 'overflow') and callable(getattr(pool, 'overflow', None)) else None
            except Exception as pool_err:
                # Fallback if method calls fail
                logging.debug(f"Could not get pool stats: {pool_err}")
                pool_size = checked_in = checked_out = overflow = None
            
            stats = {
                "status": "healthy",
                "checked": health[0] if health else 0,
                "pool_size": pool_size,
                "checked_in": checked_in,
                "checked_out": checked_out,
                "overflow": overflow,
            }

            return stats
    except Exception as e:
        logging.error(f"Pool health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


async def drain_pool():
    """Drain all connections from pool"""
    try:
        await engine.dispose()
        logging.info("Connection pool drained successfully")
    except Exception as e:
        logging.error(f"Failed to drain pool: {e}")


# ==================== CONTEXT MANAGERS ====================
@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with automatic commit/rollback"""
    session = Session()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logging.error(f"Database session error: {e}")
        raise
    finally:
        await session.close()


# ==================== INITIALIZATION ====================
async def init_db() -> None:
    """Initialize database with connection pool warm-up"""
    logging.info("Initializing database with connection pooling...")

    try:
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Warm up connection pool by acquiring and releasing connections
        logging.info("Warming up connection pool...")
        warmup_tasks = []

        for i in range(min(3, settings.DB_POOL_SIZE)):
            warmup_tasks.append(
                asyncio.create_task(warmup_connection(i))
            )

        await asyncio.gather(*warmup_tasks)

        # Check pool health
        health = await check_pool_health()
        logging.info(f"✅ Database initialized. Pool health: {health}")

    except Exception as e:
        logging.error(f"❌ Database initialization failed: {e}")
        raise


async def warmup_connection(conn_id: int):
    """Warm up a single database connection"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()  # Just fetch to verify connection works
            logging.debug(f"Connection {conn_id} warmed up successfully")
    except Exception as e:
        logging.warning(f"Failed to warm up connection {conn_id}: {e}")


async def close_db() -> None:
    """Cleanup database connections gracefully"""
    logging.info("Closing database connections...")

    try:
        # Drain connection pool
        await drain_pool()
        logging.info("✅ Database connections closed")
    except Exception as e:
        logging.error(f"Error closing database: {e}")