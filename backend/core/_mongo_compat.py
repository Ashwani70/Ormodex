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
        """Run a MongoDB-style aggregation pipeline.

        Strategy: load the rows the leading $match selects (pushed down to SQL
        via _to_filter), then execute the remaining stages in Python. This
        faithfully supports the operators this codebase actually uses —
        $match/$group/$sum/$avg/$min/$max/$first/$last/$push/$count/$sort/
        $limit/$skip/$unwind/$addFields/$project with $sum/$cond/$ifNull
        expressions — without a partial SQL translator that silently drops
        stages. Suitable for this app's report volumes (thousands of rows).
        """
        Model = self._model()
        if Model is None:
            return []
        pipeline = list(pipeline or [])

        # Push a leading $match down to SQL so we don't load the whole table.
        sql_match = None
        if pipeline and "$match" in pipeline[0]:
            sql_match = pipeline[0]["$match"]
            pipeline = pipeline[1:]

        async with get_session() as session:
            stmt = select(Model)
            if sql_match:
                conds = _to_filter(Model, sql_match)
                if conds:
                    stmt = stmt.where(and_(*conds))
            rows = (await session.execute(stmt)).scalars().all()
        docs: list[dict] = [d for d in (_row_to_dict(r) for r in rows) if d is not None]

        for stage in pipeline:
            docs = _agg_stage(stage, docs)
        return docs

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
        self._iter_done = False
        return self

    async def __anext__(self):
        if self._iter_done:
            raise StopAsyncIteration
        self._iter_done = True
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


# ──────────────────────────────────────────────────────────────────────────────
# In-Python aggregation pipeline executor
# Supports the operators this codebase uses; see MongoCollectionCompat.aggregate.
# ──────────────────────────────────────────────────────────────────────────────

def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _resolve_path(doc: dict, path: str):
    """Resolve a dotted field path like '$items.qty' against a doc."""
    cur: Any = doc
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _eval_expr(expr, doc: dict):
    """Evaluate a $group/$project/$addFields value expression against one doc."""
    if isinstance(expr, str) and expr.startswith("$"):
        return _resolve_path(doc, expr[1:])
    if isinstance(expr, dict):
        if "$ifNull" in expr:
            a, b = expr["$ifNull"]
            val = _eval_expr(a, doc)
            return val if val is not None else _eval_expr(b, doc)
        if "$cond" in expr:
            c = expr["$cond"]
            if isinstance(c, dict):
                cond_v = _eval_cond(c["if"], doc)
                return _eval_expr(c["then"], doc) if cond_v else _eval_expr(c["else"], doc)
            if isinstance(c, list) and len(c) == 3:
                return _eval_expr(c[1], doc) if _eval_cond(c[0], doc) else _eval_expr(c[2], doc)
        if "$multiply" in expr:
            out = 1.0
            for o in expr["$multiply"]:
                out *= _num(_eval_expr(o, doc))
            return out
        if "$add" in expr:
            return sum(_num(_eval_expr(o, doc)) for o in expr["$add"])
        if "$subtract" in expr:
            a, b = expr["$subtract"]
            return _num(_eval_expr(a, doc)) - _num(_eval_expr(b, doc))
    return expr  # literal


def _eval_cond(cond, doc: dict) -> bool:
    """Evaluate a boolean expression used inside $cond."""
    if isinstance(cond, dict):
        for op, args in cond.items():
            if op in ("$eq", "$ne", "$gt", "$gte", "$lt", "$lte"):
                a, b = (_eval_expr(args[0], doc), _eval_expr(args[1], doc))
                if op == "$eq":  return a == b
                if op == "$ne":  return a != b
                if a is None or b is None:
                    return False
                if op == "$gt":  return a > b
                if op == "$gte": return a >= b
                if op == "$lt":  return a < b
                if op == "$lte": return a <= b
            if op == "$and":
                return all(_eval_cond(c, doc) for c in args)
            if op == "$or":
                return any(_eval_cond(c, doc) for c in args)
    return bool(_eval_expr(cond, doc))


def _group_key(id_spec, doc: dict):
    """Compute the (hashable) _id key for a $group stage."""
    if id_spec is None:
        return None
    if isinstance(id_spec, str):
        return _eval_expr(id_spec, doc)
    if isinstance(id_spec, dict):
        # composite key → tuple of (field, value), preserving the spec for output
        return tuple(sorted((k, _make_hashable(_eval_expr(v, doc))) for k, v in id_spec.items()))
    return id_spec


def _make_hashable(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str, sort_keys=True)
    return v


def _apply_accumulator(acc_spec: dict, docs: list[dict]):
    """Compute one $group accumulator (e.g. {'$sum': '$total'}) over a bucket."""
    (op, arg), = acc_spec.items()
    if op == "$sum":
        if arg == 1:
            return len(docs)
        return round(sum(_num(_eval_expr(arg, d)) for d in docs), 6)
    if op == "$avg":
        vals = [_num(_eval_expr(arg, d)) for d in docs]
        return round(sum(vals) / len(vals), 6) if vals else 0.0
    if op == "$min":
        vals = [_eval_expr(arg, d) for d in docs if _eval_expr(arg, d) is not None]
        return min(vals) if vals else None
    if op == "$max":
        vals = [_eval_expr(arg, d) for d in docs if _eval_expr(arg, d) is not None]
        return max(vals) if vals else None
    if op == "$first":
        return _eval_expr(arg, docs[0]) if docs else None
    if op == "$last":
        return _eval_expr(arg, docs[-1]) if docs else None
    if op == "$push":
        return [_eval_expr(arg, d) for d in docs]
    if op == "$addToSet":
        seen, out = set(), []
        for d in docs:
            v = _eval_expr(arg, d)
            h = _make_hashable(v)
            if h not in seen:
                seen.add(h); out.append(v)
        return out
    if op == "$count":
        return len(docs)
    return None


def _agg_stage(stage: dict, docs: list[dict]) -> list[dict]:
    (op, spec), = stage.items()

    if op == "$match":
        Conds = spec
        return [d for d in docs if _doc_matches(d, Conds)]

    if op == "$group":
        id_spec = spec.get("_id")
        buckets: dict = {}
        order: list = []
        for d in docs:
            key = _make_hashable(_group_key(id_spec, d))
            if key not in buckets:
                buckets[key] = []
                order.append((key, _group_key(id_spec, d)))
            buckets[key].append(d)
        out = []
        for key, raw_key in order:
            bucket = buckets[key]
            # Reconstruct _id output (composite dict, scalar, or None)
            if isinstance(id_spec, dict):
                _id_out = {k: _eval_expr(v, bucket[0]) for k, v in id_spec.items()}
            else:
                _id_out = _eval_expr(id_spec, bucket[0]) if isinstance(id_spec, str) else id_spec
            row = {"_id": _id_out}
            for field, acc in spec.items():
                if field == "_id":
                    continue
                row[field] = _apply_accumulator(acc, bucket)
            out.append(row)
        return out

    if op == "$unwind":
        path = spec["path"][1:] if isinstance(spec, dict) else spec[1:]
        preserve = spec.get("preserveNullAndEmptyArrays", False) if isinstance(spec, dict) else False
        out = []
        for d in docs:
            arr = _resolve_path(d, path)
            if isinstance(arr, list) and arr:
                for el in arr:
                    nd = dict(d); nd[path] = el; out.append(nd)
            elif preserve:
                out.append(d)
        return out

    if op in ("$addFields", "$set"):
        out = []
        for d in docs:
            nd = dict(d)
            for f, e in spec.items():
                nd[f] = _eval_expr(e, d)
            out.append(nd)
        return out

    if op == "$project":
        out = []
        for d in docs:
            nd = {}
            for f, e in spec.items():
                if e in (1, True):
                    nd[f] = d.get(f)
                elif e in (0, False):
                    continue
                else:
                    nd[f] = _eval_expr(e, d)
            out.append(nd)
        return out

    if op == "$sort":
        result = list(docs)
        for field, direction in reversed(list(spec.items())):
            result.sort(key=lambda d: (d.get(field) is None, d.get(field)), reverse=(direction == -1))
        return result

    if op == "$limit":
        return docs[: int(spec)]
    if op == "$skip":
        return docs[int(spec):]
    if op == "$count":
        return [{spec: len(docs)}]

    # Unknown stage → pass through unchanged (logged elsewhere if needed).
    return docs


def _doc_matches(doc: dict, q: dict) -> bool:
    """Python-side evaluation of a Mongo filter (for $match on derived docs)."""
    for k, v in q.items():
        if k == "$or":
            if not any(_doc_matches(doc, sub) for sub in v):
                return False
            continue
        if k == "$and":
            if not all(_doc_matches(doc, sub) for sub in v):
                return False
            continue
        actual = _resolve_path(doc, k)
        if isinstance(v, dict):
            for op, val in v.items():
                if op == "$in" and actual not in val: return False
                elif op == "$nin" and actual in val: return False
                elif op == "$ne" and actual == val: return False
                elif op == "$eq" and actual != val: return False
                elif op in ("$gt", "$gte", "$lt", "$lte"):
                    if actual is None: return False
                    if op == "$gt" and not (actual > val): return False
                    if op == "$gte" and not (actual >= val): return False
                    if op == "$lt" and not (actual < val): return False
                    if op == "$lte" and not (actual <= val): return False
        else:
            if actual != v:
                return False
    return True


class _MongoDBCompat:
    """Top-level `db` object. Attribute access returns a MongoCollectionCompat."""

    def __getattr__(self, name: str) -> MongoCollectionCompat:
        return MongoCollectionCompat(name)

    def __getitem__(self, name: str) -> MongoCollectionCompat:
        return MongoCollectionCompat(name)


# Exported singleton — all routers import this via `from core.db import db`
db = _MongoDBCompat()
