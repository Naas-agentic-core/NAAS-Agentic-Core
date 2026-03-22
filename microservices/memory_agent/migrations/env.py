import asyncio
import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# --- 1. ENVIRONMENT BOOTSTRAP ---
# Ensure we can import the app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
sys.path.append(root_dir)

# Import Service Specific Models and Settings
# adjustments may be needed depending on service structure
try:
    from microservices.memory_agent.models import *  # noqa
    from microservices.memory_agent.settings import get_settings
except ImportError as e:
    print(f"Error importing service modules: {e}")
    sys.exit(1)

settings = get_settings()

# --- 2. LOGGING CONFIGURATION ---
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# --- 3. METADATA CONFIGURATION ---
target_metadata = SQLModel.metadata

# --- 4. SCHEMA CONFIGURATION ---
target_schema = "memory"

# --- 5. MIGRATION MODES ---

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        # Only include tables in the target schema
        if object.schema != target_schema:
            return False
    return True

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=target_schema,
        include_schemas=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table_schema=target_schema,
        include_schemas=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """

    connect_args = {}
    if "postgresql" in settings.DATABASE_URL or "asyncpg" in settings.DATABASE_URL:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

    connectable = create_async_engine(
        settings.DATABASE_URL,
        echo=True,
        future=True,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        # Set search path to target schema
        if "postgresql" in settings.DATABASE_URL or "asyncpg" in settings.DATABASE_URL:
            safe_schema = target_schema.replace('"', '""')
            await connection.execute(text(f'SET search_path TO "{safe_schema}"'))
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        logger.warning("Alembic is running inside an existing event loop.")
        asyncio.ensure_future(run_async_migrations())
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
