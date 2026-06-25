"""SQLAlchemy async engine, session factory, and declarative Base for PostgreSQL."""
import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Use the localhost default when DATABASE_URL is unset OR empty/whitespace.
# (`.env` files often leave the key present-but-blank; os.environ.get's default
# only fires when the key is absent, so we must guard the empty case too — an
# empty string would otherwise crash create_async_engine with a parse error.)
_db_url = (os.environ.get("DATABASE_URL") or "").strip() \
    or "postgresql+asyncpg://postgres:postgres@localhost:5432/gravity_erp"
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    _db_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


@asynccontextmanager
async def get_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db():
    await engine.dispose()


# Compatibility shim: `from core.db import db` keeps working in all routers
# while core/ is fully migrated to SQLAlchemy.  Import lazily to avoid
# circular-import at module parse time (compat needs schema, schema needs Base).
def __getattr__(name):
    if name == "db":
        from ._mongo_compat import db as _db
        return _db
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
