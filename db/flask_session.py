"""
Synchronous database session for Flask
This avoids event loop conflicts with Flask's asgiref wrapper
"""

from __future__ import annotations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
import logging
from config import settings
from .models import Base

# Import all models to ensure they're registered with Base.metadata


def create_sync_engine():
    """Create synchronous SQLAlchemy engine for Flask"""
    # Convert async URL to sync URL
    database_url = settings.database_url
    if database_url.startswith("postgresql+asyncpg://"):
        # Replace asyncpg with psycopg2 (synchronous)
        database_url = database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )
    elif database_url.startswith("postgresql://"):
        # Already sync, but ensure psycopg2
        if "+" not in database_url.split("://")[1].split("@")[0]:
            database_url = database_url.replace(
                "postgresql://", "postgresql+psycopg2://"
            )

    pool_config = {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_pre_ping": settings.DB_POOL_PRE_PING,
        "echo": settings.DB_ECHO,
    }

    engine = create_engine(database_url, **pool_config)

    return engine


# Create sync engine
sync_engine = create_sync_engine()

# Create session factory
SyncSession = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=True,
    expire_on_commit=False,
)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Get synchronous database session with automatic commit/rollback"""
    session = SyncSession()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


def init_sync_db() -> None:
    """Initialize database tables (synchronous)"""
    logging.info("Initializing database tables (sync mode for Flask)...")

    try:
        # Create tables
        with sync_engine.begin() as conn:
            # Make sure schema exists and is selected (Postgres)
            if "postgresql" in settings.database_url.lower():
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
                conn.execute(text("SET search_path TO public"))
                # Set schema for tables
                for table in Base.metadata.tables.values():
                    if table.schema is None:
                        table.schema = "public"
            Base.metadata.create_all(conn)

        logging.info("✅ Database tables initialized (sync mode)")
    except Exception as e:
        logging.error(f"❌ Database initialization failed: {e}")
        raise
