"""Alembic async environment for PostgreSQL migrations."""
import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context  # type: ignore[attr-defined]
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import Base  # noqa: E402

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or config.get_main_option("sqlalchemy.url")
        or "postgresql+asyncpg://postgres:postgres@localhost:5432/gravity_erp"
    )
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(url=_db_url(), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    eng = create_async_engine(_db_url(), poolclass=pool.NullPool)
    async with eng.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await eng.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
