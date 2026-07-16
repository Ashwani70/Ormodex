"""SQLAlchemy async engine, session factory, and declarative Base for PostgreSQL."""
import asyncio
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    # `db` is provided lazily at runtime via __getattr__ (see bottom of file);
    # declare it here so type checkers know `from core.db import db` is valid
    # and can resolve the full method chain (db.coll.find().to_list() etc.).
    from ._mongo_compat import _MongoDBCompat
    db: _MongoDBCompat

# Use the localhost default when DATABASE_URL is unset OR empty/whitespace.
# (`.env` files often leave the key present-but-blank; os.environ.get's default
# only fires when the key is absent, so we must guard the empty case too — an
# empty string would otherwise crash create_async_engine with a parse error.)
_db_url = (os.environ.get("DATABASE_URL") or "").strip() \
    or "postgresql+asyncpg://postgres:postgres@localhost:5432/gravity_erp"

# Fail fast with an actionable message if DATABASE_URL is not a Postgres URI.
# A common mistake is pasting the Supabase auth/JWKS URL (https://...) here, which
# would otherwise crash deep inside SQLAlchemy with "Can't load plugin: ...:https".
if _db_url.startswith(("http://", "https://")):
    raise RuntimeError(
        "DATABASE_URL is set to an http(s) URL, not a Postgres connection string. "
        "Use the Supabase Postgres URI from Settings → Database → Connection string "
        "(e.g. postgresql://postgres:[PASSWORD]@db.<ref>.supabase.co:5432/postgres), "
        "NOT the auth/JWKS endpoint."
    )
if "[YOUR-DB-PASSWORD]" in _db_url or "[PASSWORD]" in _db_url or "[YOUR-PASSWORD]" in _db_url:
    raise RuntimeError(
        "DATABASE_URL still contains the password placeholder. Replace "
        "[YOUR-PASSWORD] in backend/.env with your real Supabase database password."
    )

if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

# Detect the Supabase Supavisor connection pooler. The direct host
# (db.<ref>.supabase.co:5432) is IPv6-only and slow/flaky to dial from IPv4
# networks; the pooler (aws-*.pooler.supabase.com, transaction port 6543) is
# IPv4-reachable and keeps warm server-side connections. Two adjustments are
# required when going through it:
#   1. Transaction-mode pooling multiplexes one server connection across many
#      clients, so prepared statements (asyncpg's default) break. Disable the
#      statement cache and give each one a unique name to be safe.
#   2. The pooler already pools, so SQLAlchemy should NOT keep its own pool of
#      long-lived connections — use NullPool and let the pooler manage them.
_is_pooler = "pooler.supabase.com" in _db_url or ":6543" in _db_url

_engine_kwargs: dict = {"echo": False}
if _is_pooler:
    import uuid

    # Keep a small WARM pool of client→pooler connections. The compat data layer
    # opens a fresh session per call, so a chatty endpoint (the dashboard makes
    # ~15 queries) would, under NullPool, do ~15 full TLS handshakes to the
    # pooler. From an IPv4 network to the cross-region pooler that handshake is
    # 1.5–6s EACH (measured), so the request took ~30s+ and routinely tripped the
    # connect timeout → 500 "Failed to load …". A real pool dials once and reuses
    # the connection, turning per-query cost from seconds into ~0.
    #
    # Supabase transaction-mode pooling (port 6543) still forbids prepared
    # statements (it multiplexes one server conn across clients), so the
    # statement cache stays off with unique prepared-statement names. The pooled
    # connections are client→Supavisor, which is exactly what Supavisor expects.
    _engine_kwargs.update(
        # 10 warm connections cover a 10-tab browser session with concurrent
        # dashboard fan-outs; overflow handles brief spikes.
        pool_size=10,
        max_overflow=10,
        pool_timeout=30,
        # pool_pre_ping=True: a SELECT 1 on checkout catches stale connections
        # (Supabase Supavisor idle-closes them after ~5 min on free tier).
        # Without this, a stale connection raises ConnectionDoesNotExistError
        # mid-request → 500. The ~30ms cost per checkout is cheaper than a 500.
        pool_pre_ping=True,
        # Recycle well under Supabase's idle timeout (5 min free, 30 min paid).
        # 240s (4 min) ensures the pool never holds a connection long enough for
        # the Supavisor to drop it on the server side.
        pool_recycle=240,
    )
    # ── Supabase transaction-mode pooler (Supavisor, :6543) + asyncpg ──
    # Transaction pooling multiplexes ONE server backend across many clients per
    # statement, so a prepared statement created on backend A is gone when the
    # next query lands on backend B → `InvalidSQLStatementNameError: prepared
    # statement "__asyncpg_…" does not exist`. This surfaced as INTERMITTENT 500s
    # ("dashboard loads, then categories/module fails to load").
    #
    # Disabling asyncpg's own cache (statement_cache_size=0) is NOT enough: the
    # SQLAlchemy asyncpg dialect keeps its OWN prepared-statement cache (default
    # 100), and reuses those handles across pooled connections. We must disable
    # BOTH. With both caches off, every statement is unnamed/one-shot, which is
    # exactly what a transaction pooler requires.
    _engine_kwargs["connect_args"] = {
        # asyncpg-level cache off.
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        # Allow for the slow cross-region TLS handshake when the pool actually
        # needs to open a new connection. Reused connections pay this once.
        "timeout": 30,
    }
    # SQLAlchemy's asyncpg dialect keeps its OWN prepared-statement cache
    # (default 100), separate from asyncpg's. Force it to 0 so the dialect
    # never reuses a prepared-statement handle across the transaction pooler's
    # multiplexed backends.
    sep = "&" if "?" in _db_url else "?"
    if "prepared_statement_cache_size" not in _db_url:
        _db_url = f"{_db_url}{sep}prepared_statement_cache_size=0"
else:
    # Direct connection — pre_ping catches stale connections without the
    # prepared-statement complications of the transaction pooler.
    _engine_kwargs.update(
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=240,
        connect_args={"timeout": 15},
    )

engine = create_async_engine(_db_url, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Per-query timing instrumentation ─────────────────────────────────────────
# Logs the wall-clock time of every SQL statement. Against a cross-region pooler
# the dominant cost is network round-trips, so this is the fastest way to see
# which endpoints are chatty (many fast queries) vs which run a genuinely slow
# query. Set SQL_TIMING_LOG=1 to log EVERY query; otherwise only statements
# slower than SQL_SLOW_MS (default 200ms — i.e. ~one cross-region round-trip) are
# logged as warnings. Disable entirely with SQL_TIMING=0.
import logging as _logging
import time as _time

from sqlalchemy import event as _event
from sqlalchemy.engine import Engine as _Engine

_sql_logger = _logging.getLogger("sql.timing")
_SQL_TIMING_ENABLED = os.environ.get("SQL_TIMING", "1").lower() not in ("0", "false", "no")
_SQL_LOG_ALL = os.environ.get("SQL_TIMING_LOG", "").lower() in ("1", "true", "yes")
_SQL_SLOW_MS = float(os.environ.get("SQL_SLOW_MS", "200"))

# Aggregate counters so a request-level middleware / diagnostics endpoint can
# report "this request issued N queries totalling M ms" — the round-trip count is
# the real KPI here.
_query_stats = {"count": 0, "total_ms": 0.0, "slow": 0}


def query_stats() -> dict:
    return dict(_query_stats)


if _SQL_TIMING_ENABLED:

    @_event.listens_for(_Engine, "before_cursor_execute")
    def _before_cursor_execute(_conn, _cursor, _statement, _parameters, context, _executemany):  # noqa: ANN001
        context._query_start_time = _time.perf_counter()

    @_event.listens_for(_Engine, "after_cursor_execute")
    def _after_cursor_execute(_conn, _cursor, statement, _parameters, context, _executemany):  # noqa: ANN001
        start = getattr(context, "_query_start_time", None)
        if start is None:
            return
        elapsed_ms = (_time.perf_counter() - start) * 1000.0
        _query_stats["count"] += 1
        _query_stats["total_ms"] += elapsed_ms
        is_slow = elapsed_ms >= _SQL_SLOW_MS
        if is_slow:
            _query_stats["slow"] += 1
        if _SQL_LOG_ALL or is_slow:
            # Collapse whitespace and truncate so logs stay readable.
            stmt = " ".join(statement.split())[:160]
            level = _logging.WARNING if is_slow else _logging.DEBUG
            _sql_logger.log(level, "%.1fms  %s", elapsed_ms, stmt)


class Base(DeclarativeBase):
    pass


# One AsyncSession per HTTP request — reused by every db.* / get_session() call
# inside that request so a dashboard page costs 1 pooled connection instead of
# 15–30 TLS handshakes to the Supabase pooler.
_request_session: ContextVar[Optional[AsyncSession]] = ContextVar(
    "_request_session", default=None
)


def bind_request_session(session: AsyncSession):
    """Set by request middleware; returns the ContextVar token for reset()."""
    return _request_session.set(session)


def unbind_request_session(token) -> None:
    _request_session.reset(token)


@asynccontextmanager
async def get_session():
    req_sess = _request_session.get()
    if req_sess is not None:
        yield req_sess
        return

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db():
    await engine.dispose()


async def warm_pool(n: int | None = None) -> None:
    """Pre-open pool connections so the first request burst does not queue on TLS.

    Cross-region cold-connect cost is the worst latency cliff in this app: a NEW
    client→pooler connection costs ~6s (TLS + auth handshake to Singapore),
    versus ~260ms to reuse a warm one. A page that fans out ~10 parallel API
    calls against a pool with only a few warm connections forces the rest to pay
    that 6s cliff *concurrently with the user waiting* — this is the dominant
    cause of 30–60s first loads. So we warm the FULL configured pool_size up
    front. We do it in PARALLEL (asyncio.gather) so total boot delay is ~one
    cold-connect (~6s), not pool_size of them sequentially (which previously
    added 30–60s and is why warmup used to be capped at 6).
    """
    from sqlalchemy import text

    if n is not None:
        target = n
    else:
        # Warm the whole steady-state pool so the first real request burst never
        # has to open a connection. Overflow (max_overflow) is left to open
        # lazily under genuine spikes; the base pool_size covers a normal page.
        target = _engine_kwargs.get("pool_size") or 5

    async def _ping_one() -> None:
        conn = await engine.connect()
        try:
            await conn.execute(text("SELECT 1"))
        finally:
            await conn.close()

    # All in parallel: wall-clock cost ≈ a single cold connect, not target × it.
    await asyncio.gather(*(_ping_one() for _ in range(target)), return_exceptions=True)


# Compatibility shim: `from core.db import db` keeps working in all routers
# while core/ is fully migrated to SQLAlchemy.  Import lazily to avoid
# circular-import at module parse time (compat needs schema, schema needs Base).
def __getattr__(name):
    if name == "db":
        from ._mongo_compat import db as _db
        return _db
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
