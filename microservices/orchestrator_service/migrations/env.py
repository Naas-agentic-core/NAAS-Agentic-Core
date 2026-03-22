import asyncio
import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

# --- 1. ENVIRONMENT BOOTSTRAP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
sys.path.append(root_dir)

# Import Service Specific Models and Settings
try:
    from microservices.orchestrator_service.src.models.mission import *  # noqa
    from microservices.orchestrator_service.src.models.mission import OrchestratorSQLModel
    from microservices.orchestrator_service.src.core.config import get_settings
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
target_metadata = OrchestratorSQLModel.metadata

# --- 4. SCHEMA CONFIGURATION ---
target_schema = "orchestrator"

# --- 5. MIGRATION MODES ---

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        if object.schema != target_schema:
            return False
    return True

def run_migrations_offline() -> None:
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
        if "postgresql" in settings.DATABASE_URL or "asyncpg" in settings.DATABASE_URL:
            safe_schema = target_schema.replace('"', '""')
            await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{safe_schema}"'))
            await connection.execute(text(f'SET search_path TO "{safe_schema}"'))
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
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
