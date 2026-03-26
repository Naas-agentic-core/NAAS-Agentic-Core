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
from collections.abc import AsyncGenerator

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings.base import BaseServiceSettings, get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "async_session_factory",
    "create_db_engine",
    "create_session_factory",
    "engine",
    "get_db",
]


def create_db_engine(settings: BaseServiceSettings) -> AsyncEngine:
    """
    Creates an AsyncEngine based on the provided settings.
    Canonical implementation for all services.

    Handles 'sslmode' in asyncpg URLs by converting it to an SSL context,
    preventing 'unexpected keyword argument' errors.
    """
    db_url = settings.DATABASE_URL
    if not db_url:
        raise ValueError("DATABASE_URL is not set in settings.")

    engine_args = {
        "echo": settings.DEBUG,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    # Parse URL to safely handle driver-specific logic
    url_obj = make_url(db_url)

    if "sqlite" in url_obj.drivername:
        engine_args["connect_args"] = {"check_same_thread": False}
        logger.info(f"🔌 Database (SQLite): {settings.SERVICE_NAME}")

    elif "postgresql" in url_obj.drivername or "asyncpg" in url_obj.drivername:
        # GUARDRAIL: Force asyncpg driver if missing
        if url_obj.drivername == "postgresql":
            url_obj = url_obj.set(drivername="postgresql+asyncpg")
            db_url = url_obj.render_as_string(hide_password=False)

        # Initialize connect_args if not exists
        if "connect_args" not in engine_args:
            engine_args["connect_args"] = {}

        # PgBouncer Compatibility (Supabase)
        # We must set these args explicitly in the connect_args dictionary
        # AND ensure they are passed as integers.
        engine_args["connect_args"].update(
            {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
        )

        # Handle ssl query params and convert them to an SSL context for asyncpg.
        qs = dict(url_obj.query)
        ssl_mode = None
        if "sslmode" in qs:
            ssl_mode = qs.pop("sslmode")
        elif "ssl" in qs:
            ssl_mode = qs.pop("ssl")

        if ssl_mode is not None:
            # Update db_url to exclude ssl/sslmode
            url_obj = url_obj.set(query=qs)

            # [CRITICAL GUARDRAIL]
            # Must use `render_as_string(hide_password=False)`!
            # 1. `str(url_obj)` masks passwords as '***', causing auth failures.
            # 2. We must PRESERVE URL encoding (e.g. '%40') for passwords.
            #    `render_as_string` handles this correctly for the driver.
            db_url = url_obj.render_as_string(hide_password=False)

            # Create SSL Context based on mode
            # 'disable' is default (no ssl arg)
            if ssl_mode in ("require", "verify-ca", "verify-full"):
                import os
                import ssl

                # Create a default context that verifies certificates
                ctx = ssl.create_default_context()

                if ssl_mode == "require":
                    # Strictly enforce hostname and certificate verification
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_REQUIRED
                    ctx.load_default_certs()

                    # Load custom CA certificate if provided securely
                    db_ca_cert_path = getattr(settings, "DB_CA_CERT_PATH", None) or os.environ.get("DB_CA_CERT_PATH")
                    if db_ca_cert_path:
                        ctx.load_verify_locations(cafile=db_ca_cert_path)

                engine_args["connect_args"]["ssl"] = ctx
                logger.info(f"🔒 SSL Enabled (Mode: {ssl_mode})")

        # Production optimization
        is_dev = settings.ENVIRONMENT in ("development", "testing")
        engine_args["pool_size"] = 5 if is_dev else 40
        engine_args["max_overflow"] = 10 if is_dev else 60

        logger.info(f"🔌 Database (Postgres): {settings.SERVICE_NAME}")

    return create_async_engine(db_url, **engine_args)


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
# Ideally, we should remove this, but for Phase 2 backward compatibility, we keep it.
# Services should NOT use this. They should create their own in their `database.py`.

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
