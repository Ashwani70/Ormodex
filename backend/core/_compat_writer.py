"""Temporary script — write the MongoDB→SQLAlchemy compatibility shim."""
import os

BASE = os.path.dirname(__file__)

# ── _mongo_compat.py ─────────────────────────────────────────────────────────
COMPAT = '''\
"""MongoDB-to-SQLAlchemy compatibility shim.

Provides a `db` object where `db.collection_name` returns a
MongoCollectionCompat wrapper that exposes the MongoDB-style async API
(find_one, find, insert_one, update_one, delete_one, count_documents, …)
but executes via SQLAlchemy AsyncSession.

This lets the 50+ routers keep their existing MongoDB-style calls while
the core layer has been fully migrated to SQLAlchemy.

Usage in routers (unchanged from before):
    from core.db import db
    user = await db.users.find_one({"email": email})
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, func, update, delete, and_, or_, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import get_session
from .utils import _table, _row_to_dict, new_id, now_iso


def _to_filter(Model, q: dict):
    """Convert a flat MongoDB-style filter dict into SQLAlchemy WHERE conditions.

    Supported:
      - {"field": value}          → field == value
      - {"field": {"$in": [...]}} → field.in_(...)
      - {"field": {"$ne": v}}     → field != v
      - {"field": {"$lt": v}}     → field < v
      - {"field": {"$lte": v}}    → field <= v
      - {"field": {"$gt": v}}     → field > v
      - {"field": {"$gte": v}}    → field >= v
      - {"field": {"$regex": v}}  → field LIKE v (% substituted)
      - {"$or": [...]}            → OR(...)
      - {"$and": [...]}           → AND(...)
    """
    conds = []
    for k, v in q.items():
        if k == "$or":
            conds.append(or_(*[and_(*_to_filter(Model, sub)) for sub in v]))
            continue
        if k == "$and":
            conds.append(and_(*[and_(*_to_filter(Model, sub)) for sub in v]))
            continue
        if k == "_id":
            continue  # MongoDB _id — ignored
        col = getattr(Model, k, None)
        if col is None:
            continue
        if isinstance(v, dict):
            sub_conds = []
            for op, val in v.items():
                if op == "$in":
                    sub_conds.append(col.in_(val))
                elif op == "$nin":
                    sub_conds.append(col.notin_(val))
                elif op == "$ne":
                    sub_conds.append(col != val)
                elif op == "$lt":
                    sub_conds.append(col < val)
                elif op == "$lte":
                    sub_conds.append(col <= val)
                elif op == "$gt":
                    sub_conds.append(col > val)
                elif op == "$gte":
                    sub_conds.append(col >= val)
                elif op in ("$regex", "$regularExpression"):
                    # Convert simple regex to LIKE
                    pattern = val if isinstance(val, str) else val.get("pattern", "")
                    pattern = pattern.replace(".*", "%").replace(".+", "%")
                    if not (pattern.startswith("%") or pattern.startswith("^")):
                        pattern = "%" + pattern
                    pattern = pattern.lstrip("^").rstrip("$")
                    if not pattern.endswith("%"):
                        pattern = pattern + "%"
                    sub_conds.append(col.ilike(pattern))
                elif op == "$exists":
                    if val:
                        sub_conds.append(col != None)
                    else:
                        sub_conds.append(col == None)
            conds.extend(sub_conds)
        else:
            conds.append(col == v)
    return conds


def _apply_set_update(row, update_doc: dict):
    """Apply MongoDB $set / $unset to an ORM row in-place."""
    if "$set" in update_doc:
        for k, v in update_doc["$set"].items():
            if hasattr(row, k):
                setattr(row, k, v)
    if "$unset" in update_doc:
        for k in update_doc["$unset"]:
            if hasattr(row, k):
                setattr(row, k, None)
    if "$push" in update_doc:
        for k, v in update_doc["$push"].items():
            if hasattr(row, k):
                current = getattr(row, k) or []
                if isinstance(current, list):
                    current = current + [v]
                    setattr(row, k, current)
    if "$pull" in update_doc:
        for k, v in update_doc["$pull"].items():
            if hasattr(row, k):
                current = getattr(row, k) or []
                if isinstance(current, list):
                    current = [i for i in current if i != v]
                    setattr(row, k, current)
    if "$inc" in update_doc:
        for k, v in update_doc["$inc"].items():
            if hasattr(row, k):
                current = getattr(row, k) or 0
                setattr(row, k, current + v)
    # Direct field update (no operator prefix)
    for k, v in update_doc.items():
        if not k.startswith("$") and hasattr(row, k):
            setattr(row, k, v)


class MongoCursorCompat:
    """Async-iterable cursor returned by find()."""

    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, length=None) -> list[dict]:
        rows = self._rows if length is None else self._rows[:length]
        return [_row_to_dict(r) for r in rows]

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return _row_to_dict(row)


class MongoCollectionCompat:
    """Wraps a single SQLAlchemy model with MongoDB-style async methods."""

    def __init__(self, collection_name: str):
        self._name = collection_name

    def _model(self):
        try:
            return _table(self._name)
        except ValueError:
            return None

    async def find_one(self, q: dict = None, projection: dict = None) -> Optional[dict]:
        Model = self._model()
        if Model is None:
            return None
        async with get_session() as session:
            stmt = select(Model)
            if q:
                conds = _to_filter(Model, q)
                if conds:
                    stmt = stmt.where(and_(*conds))
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row is None:
                return None
            d = _row_to_dict(row)
            if projection:
                exclude = [k for k, v in projection.items() if v == 0]
                for k in exclude:
                    d.pop(k, None)
            return d

    def find(self, q: dict = None, projection: dict = None) -> "MongoFindBuilder":
        return MongoFindBuilder(self._model(), q or {}, projection)

    async def insert_one(self, doc: dict) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeInsertResult(doc.get("id", new_id()))
        if "id" not in doc or not doc["id"]:
            doc["id"] = new_id()
        doc.setdefault("created_at", now_iso())
        doc.setdefault("updated_at", now_iso())
        async with get_session() as session:
            row = Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})
            session.add(row)
        return _FakeInsertResult(doc["id"])

    async def insert_many(self, docs: list) -> Any:
        Model = self._model()
        if Model is None:
            return None
        now = now_iso()
        async with get_session() as session:
            for doc in docs:
                doc.setdefault("id", new_id())
                doc.setdefault("created_at", now)
                doc.setdefault("updated_at", now)
                row = Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})
                session.add(row)
        return None

    async def update_one(self, q: dict, update_doc: dict, upsert: bool = False) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeUpdateResult(0)
        async with get_session() as session:
            stmt = select(Model)
            conds = _to_filter(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row is None:
                if upsert:
                    doc = {}
                    _apply_set_update(doc, update_doc)
                    doc.setdefault("id", new_id())
                    doc.setdefault("created_at", now_iso())
                    doc["updated_at"] = now_iso()
                    new_row = Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})
                    session.add(new_row)
                    return _FakeUpdateResult(0, upserted_id=doc["id"])
                return _FakeUpdateResult(0)
            _apply_set_update(row, update_doc)
            if hasattr(row, "updated_at"):
                row.updated_at = now_iso()
        return _FakeUpdateResult(1)

    async def update_many(self, q: dict, update_doc: dict) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeUpdateResult(0)
        async with get_session() as session:
            stmt = select(Model)
            conds = _to_filter(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                _apply_set_update(row, update_doc)
                if hasattr(row, "updated_at"):
                    row.updated_at = now_iso()
        return _FakeUpdateResult(len(rows))

    async def delete_one(self, q: dict) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeDeleteResult(0)
        async with get_session() as session:
            stmt = select(Model)
            conds = _to_filter(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row:
                await session.delete(row)
                return _FakeDeleteResult(1)
        return _FakeDeleteResult(0)

    async def delete_many(self, q: dict) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeDeleteResult(0)
        async with get_session() as session:
            stmt = select(Model)
            conds = _to_filter(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            rows = result.scalars().all()
            count = 0
            for row in rows:
                await session.delete(row)
                count += 1
        return _FakeDeleteResult(count)

    async def count_documents(self, q: dict = None) -> int:
        Model = self._model()
        if Model is None:
            return 0
        async with get_session() as session:
            stmt = select(func.count()).select_from(Model)
            if q:
                conds = _to_filter(Model, q)
                if conds:
                    stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            return result.scalar_one()

    async def aggregate(self, pipeline: list) -> list:
        """Very limited aggregate support — returns [] for unsupported pipelines."""
        return []

    async def replace_one(self, q: dict, replacement: dict, upsert: bool = False) -> Any:
        return await self.update_one(q, replacement, upsert=upsert)

    async def distinct(self, field: str, q: dict = None) -> list:
        Model = self._model()
        if Model is None:
            return []
        col = getattr(Model, field, None)
        if col is None:
            return []
        async with get_session() as session:
            stmt = select(col).distinct()
            if q:
                conds = _to_filter(Model, q)
                if conds:
                    stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            return [r for (r,) in result.all() if r is not None]

    async def create_index(self, *args, **kwargs):
        pass  # Indexes are handled by Alembic / create_all


class MongoFindBuilder:
    """Builder returned by collection.find() — supports .to_list(), .sort(), .skip(), .limit()."""

    def __init__(self, Model, q: dict, projection: dict = None):
        self._Model = Model
        self._q = q
        self._projection = projection
        self._sort = []
        self._skip_n = 0
        self._limit_n = 0

    def sort(self, field_or_list, direction=None):
        if isinstance(field_or_list, list):
            self._sort = field_or_list
        else:
            self._sort = [(field_or_list, direction or 1)]
        return self

    def skip(self, n: int):
        self._skip_n = n
        return self

    def limit(self, n: int):
        self._limit_n = n
        return self

    async def to_list(self, length=None) -> list[dict]:
        if self._Model is None:
            return []
        async with get_session() as session:
            stmt = select(self._Model)
            conds = _to_filter(self._Model, self._q)
            if conds:
                stmt = stmt.where(and_(*conds))
            for field, direction in self._sort:
                col = getattr(self._Model, field, None)
                if col is not None:
                    stmt = stmt.order_by(col.desc() if direction == -1 else col.asc())
            if self._skip_n:
                stmt = stmt.offset(self._skip_n)
            lim = length if length is not None else (self._limit_n or None)
            if lim:
                stmt = stmt.limit(lim)
            result = await session.execute(stmt)
            rows = result.scalars().all()
        out = [_row_to_dict(r) for r in rows]
        if self._projection:
            exclude = [k for k, v in self._projection.items() if v == 0]
            out = [{k: v for k, v in d.items() if k not in exclude} for d in out]
        return out

    def __aiter__(self):
        self._rows = None  # reset on each new iteration
        return self

    async def __anext__(self):
        if self._rows is None:
            rows = await self.to_list()
            self._rows = iter(rows)
        try:
            return next(self._rows)
        except StopIteration:
            raise StopAsyncIteration


class _FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _FakeUpdateResult:
    def __init__(self, matched_count, upserted_id=None):
        self.matched_count = matched_count
        self.modified_count = matched_count
        self.upserted_id = upserted_id


class _FakeDeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class _MongoDBCompat:
    """Top-level `db` object. Attribute access returns a MongoCollectionCompat."""

    def __getattr__(self, name: str) -> MongoCollectionCompat:
        return MongoCollectionCompat(name)

    def __getitem__(self, name: str) -> MongoCollectionCompat:
        return MongoCollectionCompat(name)


# Exported singleton — all routers import this via `from core.db import db`
db = _MongoDBCompat()
'''

path = os.path.join(BASE, "_mongo_compat.py")
with open(path, "w", encoding="utf-8") as f:
    f.write(COMPAT)
print(f"Written _mongo_compat.py: {len(COMPAT)} chars")

# Now patch db.py to re-export `db` from the compat shim
DB_PATCH = '''\
"""SQLAlchemy async engine, session factory, and declarative Base for PostgreSQL."""
import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

_db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gravity_erp")
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
'''

db_path = os.path.join(BASE, "db.py")
with open(db_path, "w", encoding="utf-8") as f:
    f.write(DB_PATCH)
print(f"Written db.py: {len(DB_PATCH)} chars")
