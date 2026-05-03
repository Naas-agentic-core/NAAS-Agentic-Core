"""
Canonical Database Factory for CogniForge.
"""

import logging
import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.settings.base import BaseServiceSettings, get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "async_session_factory",
    "create_db_engine",
    "create_session_factory",
    "engine",
    "get_db",
]


def _is_supabase_url(host: str | None, port: int | None) -> bool:
    """Return True for any Supabase connection."""
    if host and "supabase.com" in host:
        return True
    return port == 6543


def create_db_engine(settings: BaseServiceSettings) -> AsyncEngine:
    db_url = settings.DATABASE_URL
    if not db_url:
        raise ValueError("DATABASE_URL is not set in settings.")

    url_obj = make_url(db_url)

    # --- SQLite ---
    if "sqlite" in url_obj.drivername:
        logger.info(f"SQLite database: {settings.SERVICE_NAME}")
        return create_async_engine(
            db_url,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"check_same_thread": False},
        )

    # --- PostgreSQL ---
    if url_obj.drivername in ("postgresql", "postgres"):
        url_obj = url_obj.set(drivername="postgresql+asyncpg")

    # Strip ssl params from query string — we'll handle via SSL context
    qs = dict(url_obj.query)
    ssl_mode = qs.pop("sslmode", None) or qs.pop("ssl", None)

    is_supabase = _is_supabase_url(url_obj.host, url_obj.port)

    if is_supabase and url_obj.port == 6543:
        # Rewrite port 6543 (PgBouncer transaction mode) → 5432 (session mode).
        # Port 6543 uses PgBouncer which keeps prepared statement names in its
        # own cache across logical connections. This causes asyncpg to hit
        # DuplicatePreparedStatementError even with statement_cache_size=0,
        # because the collision happens at the PgBouncer protocol layer.
        # Port 5432 connects directly to the Postgres session pool on Supabase,
        # which correctly handles statement_cache_size=0.
        url_obj = url_obj.set(port=5432)
        logger.info("Rewrote Supabase port 6543 → 5432 (session mode)")

    url_obj = url_obj.set(query=qs)
    db_url = url_obj.render_as_string(hide_password=False)

    connect_args: dict = {}
    if ssl_mode in ("require", "verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if ssl_mode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx
        logger.info(f"SSL enabled (mode: {ssl_mode})")

    if is_supabase:
        # Disable prepared statement cache — required even on port 5432 because
        # pooler.supabase.com proxies still share state across connections.
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0
        logger.info(
            f"Supabase database (NullPool, no prepared statements, port {url_obj.port}): {settings.SERVICE_NAME}"
        )
        return create_async_engine(
            db_url,
            echo=settings.DEBUG,
            poolclass=NullPool,
            connect_args=connect_args,
        )

    is_dev = settings.ENVIRONMENT in ("development", "testing")
    logger.info(f"Postgres database: {settings.SERVICE_NAME}")
    return create_async_engine(
        db_url,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5 if is_dev else 40,
        max_overflow=10 if is_dev else 60,
        connect_args=connect_args,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# Global Singleton (legacy app/core usage only)
_legacy_settings = get_settings()
engine: AsyncEngine = create_db_engine(_legacy_settings)
async_session_factory = create_session_factory(engine)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
