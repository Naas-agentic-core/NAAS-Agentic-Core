import logging
import os
import ssl
from collections.abc import AsyncGenerator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from microservices.orchestrator_service.src.core.config import settings
from microservices.orchestrator_service.src.models.mission import OrchestratorSQLModel

logger = logging.getLogger(__name__)


def create_engine() -> AsyncEngine:
    db_url = settings.DATABASE_URL
    url_obj = make_url(db_url)

    engine_args = {
        "echo": False,
        "future": True,
        "connect_args": {},
    }

    qs = dict(url_obj.query)
    ssl_mode = qs.pop("sslmode", None) or qs.pop("ssl", None)

    if ssl_mode is not None:
        url_obj = url_obj.set(query=qs)
        db_url = url_obj.render_as_string(hide_password=False)

        if ssl_mode in ("require", "verify-ca", "verify-full"):
            ctx = ssl.create_default_context()
            if ssl_mode == "require":
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_REQUIRED
                ctx.load_default_certs()

                ca_cert = os.environ.get("DB_CA_CERT_PATH")
                if ca_cert and os.path.exists(ca_cert):
                    ctx.load_verify_locations(cafile=ca_cert)

            engine_args["connect_args"]["ssl"] = ctx

    # Supabase / PgBouncer compatibility
    engine_args["connect_args"].update(
        {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
    )

    return create_async_engine(db_url, **engine_args)


engine = create_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

_postgres_pool: AsyncConnectionPool | None = None
postgres_checkpointer: AsyncPostgresSaver | None = None


def get_checkpointer() -> AsyncPostgresSaver | None:
    return postgres_checkpointer


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


async def init_db() -> None:
    """Initialize database schema."""
    global _postgres_pool, postgres_checkpointer
    try:
        # Import models here or ensure they are imported before calling this
        # We rely on main.py importing them.
        async with engine.begin() as conn:
            await conn.run_sync(OrchestratorSQLModel.metadata.create_all)

        # Initialize LangGraph Postgres checkpointer pool
        # Need to re-create a proper psycopg string from settings.DATABASE_URL
        # We will use psycopg's kwargs mapping or simple asyncpg string since it is similar
        pool_kwargs = {
            "conninfo": settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        }
        _postgres_pool = AsyncConnectionPool(**pool_kwargs)
        await _postgres_pool.open()
        postgres_checkpointer = AsyncPostgresSaver(_postgres_pool)
        await postgres_checkpointer.setup()

        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def close_db() -> None:
    """Close the database and checkpointer pool."""
    if _postgres_pool:
        await _postgres_pool.close()
