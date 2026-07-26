"""Alembic async environment for PostgreSQL migrations."""
import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context  # type: ignore[attr-defined]
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import Base  # noqa: E402
# The models live in core/schema.py, not core/db.py — importing Base alone
# leaves Base.metadata EMPTY (so migration 001's create_all would create
# nothing and 003+ would fail on missing tables). Import the module for its
# registration side effect.
import core.schema  # noqa: E402,F401

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    # Only accept a real DATABASE_URL/POSTGRES_URL env var. Deliberately do
    # NOT fall back to alembic.ini's sqlalchemy.url (a localhost dev default)
    # when running migrations — a CI/production run with a missing secret
    # must fail loudly here, not silently attempt to connect to a localhost
    # Postgres that doesn't exist on the runner (which previously surfaced
    # as an opaque connection-refused traceback deep in
    # run_migrations_online()/run_async_migrations()).
    url = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()

    if not url:
        raise RuntimeError(
            "\n\n"
            "ALEMBIC CONFIG ERROR: DATABASE_URL (or POSTGRES_URL) is not set.\n"
            "\n"
            "Alembic refuses to fall back to a default/local database for\n"
            "migrations — running `alembic upgrade head` against the wrong\n"
            "database is exactly the kind of mistake this check prevents.\n"
            "\n"
            "Fix:\n"
            "  - Local dev:   set DATABASE_URL in backend/.env (see .env.example)\n"
            "  - GitHub Actions: add a DATABASE_URL repository secret\n"
            "    (Settings -> Secrets and variables -> Actions -> Secrets) and\n"
            "    reference it in the workflow step as:\n"
            "      env:\n"
            "        DATABASE_URL: ${{ secrets.DATABASE_URL }}\n"
            "\n"
            "Expected format (Supabase transaction pooler, recommended for CI/PaaS):\n"
            "  postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres\n"
        )

    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    # Mirror core/db.py's Supabase Supavisor transaction-pooler handling:
    # the pooler multiplexes connections across many backend server
    # processes, so asyncpg/SQLAlchemy's prepared-statement caching breaks
    # with "prepared statement ... does not exist". Disable it here too,
    # since Alembic builds its own engine independent of core/db.py.
    is_pooler = "pooler.supabase.com" in url or ":6543" in url
    if is_pooler and "prepared_statement_cache_size" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}prepared_statement_cache_size=0"

    return url


def run_migrations_offline() -> None:
    context.configure(url=_db_url(), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # transaction_per_migration: commit after each migration instead of one
    # all-or-nothing transaction for the whole run. A failure then stops at
    # the offending revision with everything before it applied and stamped —
    # and CONCURRENTLY index builds (autocommit_block in 003/005/018/019/021/
    # 022) don't have to re-run on retry.
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    db_url = _db_url()
    eng = create_async_engine(db_url, poolclass=pool.NullPool)
    try:
        async with eng.connect() as connection:
            # Cheap round-trip before handing off to Alembic's own migration
            # transaction — turns "asyncpg.exceptions/OSError deep inside
            # run_migrations_online()" into one readable line naming the
            # actual cause (auth, DNS/host, wrong port, SSL, etc.).
            try:
                await connection.execute(text("SELECT 1"))
            except SQLAlchemyError as exc:
                masked = db_url.split("@")[-1] if "@" in db_url else db_url
                raise RuntimeError(
                    "\n\nALEMBIC CONFIG ERROR: could not connect to the database "
                    f"at '{masked}'.\n"
                    "Check that DATABASE_URL is correct and reachable from this "
                    "runner (Supabase: use the pooler host on port 6543, not the "
                    "direct db.<ref>.supabase.co:5432 host — the latter is "
                    "IPv6-only and unreachable from most CI/PaaS networks).\n"
                    f"Underlying error: {exc}"
                ) from exc
            # The SELECT 1 autobegins a transaction on this connection. Close it
            # before handing off, or Alembic sees a transaction it doesn't own,
            # leaves its own transaction management disengaged, and
            # autocommit_block() (needed for CREATE INDEX CONCURRENTLY in
            # 003/005/018/019/021/022) fails its internal assertion.
            await connection.rollback()
            await connection.run_sync(do_run_migrations)
    finally:
        await eng.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
