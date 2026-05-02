"""
Canonical Database Factory for CogniForge.

Provides a unified Factory Pattern for creating AsyncEngines and SessionMakers.
Supports Microservices (Bounded Contexts) by allowing each service to instantiate
its own isolated DB stack based on its configuration.

Standards:
- Async First: Uses `sqlalchemy.ext.asyncio`.
- Factory Pattern: No global state for microservices; explicit `create_engine` calls.
- Connection Pooling: Configured via settings.
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


def _is_pgbouncer_url(host: str | None, port: int | None) -> bool:
    """Detect Supabase PgBouncer pooler by host/port pattern."""
    if host and "pooler.supabase.com" in host:
        return True
    if port == 6543:
        return True
    return False


def create_db_engine(settings: BaseServiceSettings) -> AsyncEngine:
    """
    Creates an AsyncEngine based on the provided settings.
    Canonical implementation for all services.

    For Supabase PgBouncer (transaction mode) connections, uses NullPool to
    avoid any prepared statement or connection reuse issues.
    """
    db_url = settings.DATABASE_URL
    if not db_url:
        raise ValueError("DATABASE_URL is not set in settings.")

    # Parse URL to safely handle driver-specific logic
    url_obj = make_url(db_url)

    if "sqlite" in url_obj.drivername:
        logger.info(f"🔌 Database (SQLite): {settings.SERVICE_NAME}")
        return create_async_engine(
            db_url,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"check_same_thread": False},
        )

    # --- PostgreSQL path ---

    # GUARDRAIL: Force asyncpg driver if missing
    if url_obj.drivername == "postgresql":
        url_obj = url_obj.set(drivername="postgresql+asyncpg")

    connect_args: dict = {}

    # Strip sslmode/ssl from query string and convert to SSL context
    qs = dict(url_obj.query)
    ssl_mode = qs.pop("sslmode", None) or qs.pop("ssl", None)
    url_obj = url_obj.set(query=qs)
    db_url = url_obj.render_as_string(hide_password=False)

    if ssl_mode in ("require", "verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if ssl_mode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx
        logger.info(f"🔒 SSL Enabled (Mode: {ssl_mode})")

    # Detect Supabase PgBouncer (transaction-mode pooler, port 6543)
    pgbouncer = _is_pgbouncer_url(url_obj.host, url_obj.port)

    if pgbouncer:
        # NullPool: never reuse connections — completely avoids prepared statement
        # conflicts with PgBouncer in transaction mode.
        connect_args.update({
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        })
        logger.info(f"🔌 Database (Supabase/PgBouncer, NullPool): {settings.SERVICE_NAME}")
        return create_async_engine(
            db_url,
            echo=settings.DEBUG,
            poolclass=NullPool,
            connect_args=connect_args,
        )

    # Standard PostgreSQL with connection pool
    is_dev = settings.ENVIRONMENT in ("development", "testing")
    logger.info(f"🔌 Database (Postgres): {settings.SERVICE_NAME}")
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
    """Creates a configured sessionmaker for the given engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# -----------------------------------------------------------------------------
# Global Singleton (For Legacy App/Core usage only)
# -----------------------------------------------------------------------------
_legacy_settings = get_settings()
engine: AsyncEngine = create_db_engine(_legacy_settings)
async_session_factory = create_session_factory(engine)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting a DB session.
    Used by the Monolith/Core only. Microservices should define their own `get_db`.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"❌ Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
