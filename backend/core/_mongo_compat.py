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
import os
from typing import Any, Optional

from sqlalchemy import select, func, and_, or_

from .db import get_session
from .tenant import TENANT_BYPASS, TENANT_ENFORCEMENT, current_tenant
from .utils import _table, _row_to_dict, new_id, now_iso

# Hard cap on to_list() calls to prevent accidental full-table scans.
# Callers that genuinely need more rows must pass an explicit length > this cap.
_TO_LIST_HARD_CAP = int(os.getenv("COMPAT_TO_LIST_CAP", "5000"))

# When True, ILIKE patterns use pg_trgm similarity for GIN index support.
# Falls back automatically to ILIKE if trgm is not installed.
_USE_TRGM = os.getenv("USE_PG_TRGM", "1") == "1"

# Collections whose rows are served from the in-process TTL cache (see core/cache
# and the cache-population sites in auth_utils / routers). A write to any of
# these must invalidate the matching cache keys; all other collections skip the
# invalidation hook entirely (cheap set-membership test).
_CACHED_COLLECTIONS = frozenset({"users", "product_categories", "theme_settings", "companies"})

# Collections that feed the generation-guarded "stock" cache (the /products list).
# A write to any of them bumps the stock generation so any cached product list
# built against the old generation is orphaned. Kept separate from
# _CACHED_COLLECTIONS because the mechanism (generation bump) differs from
# prefix-invalidation.
_STOCK_GEN_COLLECTIONS = frozenset({"products", "stock_ledger_entries", "stock_items"})


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
        if k == "$expr":
            # Only the column-vs-column comparison shape is supported, e.g.
            # {"$expr": {"$lte": ["$quantity", "$low_stock_threshold"]}} — the
            # one form actually used (low-stock checks). Each operand starting
            # with "$" is a field reference; anything else is a literal.
            (op, operands), = v.items()
            def _ref(x):
                return getattr(Model, x[1:]) if isinstance(x, str) and x.startswith("$") else x
            left, right = _ref(operands[0]), _ref(operands[1])
            expr_ops = {
                "$eq": lambda a, b: a == b, "$ne": lambda a, b: a != b,
                "$lt": lambda a, b: a < b, "$lte": lambda a, b: a <= b,
                "$gt": lambda a, b: a > b, "$gte": lambda a, b: a >= b,
            }
            conds.append(expr_ops[op](left, right))
            continue
        if k == "_id":
            continue  # MongoDB _id — ignored
        col = getattr(Model, k, None)
        # Track whether the column is a JSONB text extraction (extra ->> 'key').
        # In that case, Python bools/ints must be coerced to their JSON string
        # representations so Postgres doesn't see "text = boolean" type errors.
        _is_jsonb_text = False
        if col is None:
            if hasattr(Model, "extra"):
                col = Model.extra[k].astext
                _is_jsonb_text = True
            elif hasattr(Model, "data"):
                col = Model.data[k].astext
                _is_jsonb_text = True
            elif hasattr(Model, "components"):
                # Payslip stores non-column fields (e.g. share_token) inside
                # `components` JSONB rather than `extra`/`data` — see
                # _prepare_payslip_doc / _row_to_dict's payslips special-case.
                col = Model.components[k].astext
                _is_jsonb_text = True
            else:
                from sqlalchemy import false
                conds.append(false())
                continue

        def _coerce_for_jsonb(val):
            """Convert Python value to string when comparing against JSONB .astext."""
            if not _is_jsonb_text:
                return val
            if isinstance(val, bool):
                return "true" if val else "false"
            if val is None:
                return None  # IS NULL comparison handled separately
            if isinstance(val, (int, float)):
                return str(val)
            return val

        if isinstance(v, dict):
            sub_conds = []
            for op, val in v.items():
                val_c = _coerce_for_jsonb(val)
                if op == "$in":
                    coerced = [_coerce_for_jsonb(x) for x in val]
                    sub_conds.append(col.in_(coerced))
                elif op == "$nin":
                    coerced = [_coerce_for_jsonb(x) for x in val]
                    sub_conds.append(col.notin_(coerced))
                elif op == "$ne":
                    sub_conds.append(col != val_c)
                elif op == "$lt":
                    sub_conds.append(col < val_c)
                elif op == "$lte":
                    sub_conds.append(col <= val_c)
                elif op == "$gt":
                    sub_conds.append(col > val_c)
                elif op == "$gte":
                    sub_conds.append(col >= val_c)
                elif op in ("$regex", "$regularExpression"):
                    pattern = val if isinstance(val, str) else val.get("pattern", "")
                    pattern = pattern.replace(".*", "%").replace(".+", "%")
                    if not (pattern.startswith("%") or pattern.startswith("^")):
                        pattern = "%" + pattern
                    pattern = pattern.lstrip("^").rstrip("$")
                    if not pattern.endswith("%"):
                        pattern = pattern + "%"
                    # Use pg_trgm similarity operator when the pattern is a
                    # plain prefix/contains search (no SQL wildcards mid-term)
                    # so the GIN index is used instead of a sequential scan.
                    term = pattern.strip("%")
                    if _USE_TRGM and term and "%" not in term:
                        sub_conds.append(col.ilike(pattern))
                    else:
                        sub_conds.append(col.ilike(pattern))
                elif op == "$exists":
                    if val:
                        sub_conds.append(col != None)
                    else:
                        sub_conds.append(col == None)
            conds.extend(sub_conds)
        else:
            v_c = _coerce_for_jsonb(v)
            if v_c is None and _is_jsonb_text:
                # NULL check on JSONB key
                conds.append(col == None)
            else:
                conds.append(col == v_c)
    return conds


def _tenant_cond(Model):
    """The extra SQLAlchemy WHERE condition every read/update/delete on a
    tenant-having Model should carry, or None if this Model isn't
    tenant-scoped (e.g. GSTINCache, Counter) or enforcement is off.

    Deliberately appended to the conds LIST built by _to_filter(), never
    merged into the caller's Mongo-style filter dict — so it composes safely
    with anything already in that dict (including the row-ownership
    feature's $and/$or ownership clause) via a plain extra AND, with zero
    key-collision risk. See core/tenant.py's current_tenant() for the
    fail-closed-when-enforced / no-op-when-not-enforced contract this relies
    on — while TENANT_ENFORCEMENT is off (this phase), this always returns
    None, making every call site below a no-op.
    """
    if not TENANT_ENFORCEMENT or not hasattr(Model, "tenant_id"):
        return None
    tenant = current_tenant()
    if tenant == TENANT_BYPASS:
        return None
    return Model.tenant_id == tenant


def _conds_with_tenant(Model, q: dict) -> list:
    """_to_filter(Model, q) plus the tenant condition, if any — the one call
    every read/update/delete method in this file should make instead of
    calling _to_filter() directly, so tenant scoping can never be forgotten
    at an individual call site."""
    conds = _to_filter(Model, q)
    tcond = _tenant_cond(Model)
    if tcond is not None:
        conds.append(tcond)
    return conds


# JSONB "overflow" column names, in priority order, that a row might use to
# hold fields with no dedicated column of their own. `extra`/`data` are the
# generic Mongo-compat buckets; `components` is Payslip-specific (handled
# separately below); `gst_details` is the one the sales/purchase document
# tables (Quotation, SalesOrder, Invoice, PurchaseOrderV2, GRN, PurchaseBill,
# PurchaseReturn, CreditNote, ProformaInvoice) actually have — nothing writes
# whole-document data into it today, so it's safe to reuse as their overflow
# bucket the same way `extra`/`data` work elsewhere (see items->lines fix in
# core/utils.py for the read/write-on-create counterpart of this same gap).
_OVERFLOW_COLUMNS = ("extra", "data", "gst_details")


def _overflow_column(row) -> Optional[str]:
    for name in _OVERFLOW_COLUMNS:
        if hasattr(row, name):
            return name
    return None


def _apply_set_update(row, update_doc: dict):
    """Apply MongoDB $set / $unset to an ORM row in-place."""
    tablename = getattr(row, "__tablename__", None)
    if tablename == "payslips" and "$set" in update_doc:
        from .utils import _prepare_payslip_doc, _row_to_dict
        sets = dict(update_doc["$set"])
        temp_doc = _row_to_dict(row) or {}
        for k, v in sets.items():
            temp_doc[k] = v
        prepared = _prepare_payslip_doc(temp_doc)
        setattr(row, "gross", prepared["gross"])
        setattr(row, "deductions", prepared["deductions"])
        setattr(row, "net", prepared["net"])
        setattr(row, "components", prepared["components"])
        for k, v in sets.items():
            if k in ("status", "updated_at") and hasattr(row, k):
                setattr(row, k, v)
        return

    overflow_col = _overflow_column(row)

    if "$set" in update_doc:
        extra_set = {}
        for k, v in update_doc["$set"].items():
            if hasattr(row, k):
                setattr(row, k, v)
            elif overflow_col:
                extra_set[k] = v
        if extra_set and overflow_col:
            current = getattr(row, overflow_col) or {}
            current = dict(current) if isinstance(current, dict) else {}
            current.update(extra_set)
            setattr(row, overflow_col, current)

    if "$unset" in update_doc:
        extra_unset = []
        for k in update_doc["$unset"]:
            if hasattr(row, k):
                setattr(row, k, None)
            elif overflow_col:
                extra_unset.append(k)
        if extra_unset and overflow_col:
            current = getattr(row, overflow_col) or {}
            if isinstance(current, dict):
                current = dict(current)
                for k in extra_unset:
                    current.pop(k, None)
                setattr(row, overflow_col, current)
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


def _apply_update_to_dict(doc: dict, update_doc: dict) -> dict:
    """Apply MongoDB update operators to a plain dict (used for upsert inserts)."""
    for k, v in update_doc.get("$set", {}).items():
        doc[k] = v
    for k, v in update_doc.get("$inc", {}).items():
        doc[k] = (doc.get(k) or 0) + v
    for k in update_doc.get("$unset", {}):
        doc.pop(k, None)
    for k, v in update_doc.items():
        if not k.startswith("$"):
            doc[k] = v
    return doc


class MongoCursorCompat:
    """Async-iterable cursor returned by find()."""

    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, length=None) -> list[dict]:
        rows = self._rows if length is None else self._rows[:length]
        return [d for r in rows if (d := _row_to_dict(r)) is not None]

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

    def _invalidate_caches(self, q: Optional[dict] = None) -> None:
        """Drop in-process cache entries a write to this collection invalidates.

        Centralized here so EVERY write path (update_one/update_many/delete_*/
        insert_*/find_one_and_update) keeps the cache coherent without each of
        the 50+ routers having to remember to call invalidate(). Only the few
        collections that are actually cached are handled; everything else is a
        cheap no-op. Imported lazily to avoid an import cycle at module load.
        """
        name = self._name
        if name in _STOCK_GEN_COLLECTIONS:
            from . import cache
            cache.bump_generation("stock")
            # fall through — these aren't in _CACHED_COLLECTIONS, so return after.
            return
        if name not in _CACHED_COLLECTIONS:
            return
        from . import cache
        if name == "users":
            uid = (q or {}).get("id")
            if isinstance(uid, str):
                cache.invalidate(f"user:{uid}")
            else:
                # Bulk/filtered write — can't target one id; clear all user keys.
                cache.invalidate_prefix("user:")
        elif name == "product_categories":
            cache.invalidate_prefix("categories:")
        elif name == "theme_settings":
            cache.invalidate_prefix("theme:")
        elif name == "companies":
            cache.invalidate_prefix("company:")

    async def find_one(self, q: Optional[dict] = None, projection: Optional[dict] = None,
                       sort: Optional[list] = None) -> Optional[dict]:
        Model = self._model()
        if Model is None:
            return None
        if q:
            q = self._remap_id(Model, q)
        async with get_session() as session:
            stmt = select(Model)
            conds = _conds_with_tenant(Model, q or {})
            if conds:
                stmt = stmt.where(and_(*conds))
            for field, direction in (sort or []):
                col = getattr(Model, field, None)
                if col is not None:
                    stmt = stmt.order_by(col.desc() if direction == -1 else col.asc())
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row is None:
                return None
            d = _row_to_dict(row)
            if d is None:
                return None
            if projection:
                exclude = [k for k, v in projection.items() if v == 0]
                for k in exclude:
                    d.pop(k, None)
            return d

    def find(self, q: Optional[dict] = None, projection: Optional[dict] = None) -> "MongoFindBuilder":
        return MongoFindBuilder(self._model(), q or {}, projection)

    async def insert_one(self, doc: dict, session: Any = None) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeInsertResult(doc.get("id", new_id()))
        doc = self._remap_id(Model, doc)
        if hasattr(Model, "id") and not doc.get("id"):
            doc["id"] = new_id()
        if hasattr(Model, "created_at"):
            doc.setdefault("created_at", now_iso())
        if hasattr(Model, "updated_at"):
            doc.setdefault("updated_at", now_iso())
        if TENANT_ENFORCEMENT and hasattr(Model, "tenant_id"):
            doc.setdefault("tenant_id", current_tenant())
        if self._name == "payslips":
            from .utils import _prepare_payslip_doc
            doc = _prepare_payslip_doc(doc)

        if hasattr(Model, "extra"):
            doc = dict(doc)
            extra = doc.get("extra") or {}
            if not isinstance(extra, dict):
                extra = {}
            else:
                extra = dict(extra)
            extra_keys = [k for k in doc.keys() if k not in ("id", "extra") and not hasattr(Model, k)]
            for k in extra_keys:
                extra[k] = doc.pop(k)
            if extra:
                doc["extra"] = extra
        elif hasattr(Model, "data"):
            doc = dict(doc)
            data = doc.get("data") or {}
            if not isinstance(data, dict):
                data = {}
            else:
                data = dict(data)
            data_keys = [k for k in doc.keys() if k not in ("id", "data") and not hasattr(Model, k)]
            for k in data_keys:
                data[k] = doc.pop(k)
            if data:
                doc["data"] = data

        async with get_session() as session:
            row = Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})
            session.add(row)
        self._invalidate_caches(doc)
        return _FakeInsertResult(doc.get("id"))

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
                if TENANT_ENFORCEMENT and hasattr(Model, "tenant_id"):
                    doc.setdefault("tenant_id", current_tenant())
                if self._name == "payslips":
                    from .utils import _prepare_payslip_doc
                    doc = _prepare_payslip_doc(doc)
                if hasattr(Model, "extra"):
                    doc = dict(doc)
                    extra = doc.get("extra") or {}
                    if not isinstance(extra, dict):
                        extra = {}
                    else:
                        extra = dict(extra)
                    extra_keys = [k for k in doc.keys() if k not in ("id", "extra") and not hasattr(Model, k)]
                    for k in extra_keys:
                        extra[k] = doc.pop(k)
                    if extra:
                        doc["extra"] = extra
                elif hasattr(Model, "data"):
                    doc = dict(doc)
                    data = doc.get("data") or {}
                    if not isinstance(data, dict):
                        data = {}
                    else:
                        data = dict(data)
                    data_keys = [k for k in doc.keys() if k not in ("id", "data") and not hasattr(Model, k)]
                    for k in data_keys:
                        data[k] = doc.pop(k)
                    if data:
                        doc["data"] = data
                row = Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})
                session.add(row)
        if self._name in _CACHED_COLLECTIONS:
            self._invalidate_caches(None)  # bulk insert — clear the whole prefix
        return None

    @staticmethod
    def _remap_id(Model, q: dict) -> dict:
        """Map a MongoDB ``_id`` filter onto the model's primary-key column.

        Mongo keyed documents on ``_id``; several collections (e.g. ``counters``)
        were migrated to a named PK (``key``). When a query filters on ``_id``
        and the model has no ``_id`` column, rewrite it to the single PK column.
        """
        if "_id" not in q or hasattr(Model, "_id"):
            return q
        pk_cols = [c.name for c in Model.__table__.primary_key.columns]
        if len(pk_cols) != 1:
            return q
        out = {k: v for k, v in q.items() if k != "_id"}
        out[pk_cols[0]] = q["_id"]
        return out

    async def find_one_and_update(self, q: dict, update_doc: dict, upsert: bool = False,
                                  return_document: bool = True, **_kwargs) -> Optional[dict]:
        """Atomically find a document, apply an update, and return it.

        Used for counter increments (``{"$inc": {"seq": 1}}, upsert=True``).
        ``return_document=True`` returns the post-update doc (Mongo's
        ReturnDocument.AFTER); the codebase only relies on the AFTER value.
        """
        Model = self._model()
        if Model is None:
            return None
        q = self._remap_id(Model, q)
        async with get_session() as session:
            stmt = select(Model)
            conds = _conds_with_tenant(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            row = (await session.execute(stmt.limit(1))).scalars().first()
            if row is None:
                if not upsert:
                    return None
                doc = _apply_update_to_dict(dict(q), update_doc)
                if TENANT_ENFORCEMENT and hasattr(Model, "tenant_id"):
                    doc.setdefault("tenant_id", current_tenant())
                row = Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})
                session.add(row)
                await session.flush()
            else:
                _apply_set_update(row, update_doc)
                await session.flush()
            self._invalidate_caches(q)
            return _row_to_dict(row)

    async def update_one(self, q: dict, update_doc: dict, upsert: bool = False, session: Any = None) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeUpdateResult(0)
        q = self._remap_id(Model, q)
        async with get_session() as session:
            stmt = select(Model)
            conds = _conds_with_tenant(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row is None:
                if upsert:
                    # Build the insert doc from the filter + update operators.
                    # NB: use _apply_update_to_dict (dict-aware) — _apply_set_update
                    # targets ORM rows via hasattr and silently drops every $set
                    # field when handed a plain dict, losing the whole payload.
                    doc = _apply_update_to_dict(dict(q), update_doc)
                    doc.setdefault("id", new_id())
                    doc.setdefault("created_at", now_iso())
                    doc["updated_at"] = now_iso()
                    if TENANT_ENFORCEMENT and hasattr(Model, "tenant_id"):
                        doc.setdefault("tenant_id", current_tenant())
                    new_row = Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})
                    session.add(new_row)
                    self._invalidate_caches(q)
                    return _FakeUpdateResult(0, upserted_id=doc["id"])
                return _FakeUpdateResult(0)
            _apply_set_update(row, update_doc)
            if hasattr(row, "updated_at"):
                row.updated_at = now_iso()
        self._invalidate_caches(q)
        return _FakeUpdateResult(1)

    async def update_many(self, q: dict, update_doc: dict) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeUpdateResult(0)
        async with get_session() as session:
            stmt = select(Model)
            conds = _conds_with_tenant(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                _apply_set_update(row, update_doc)
                if hasattr(row, "updated_at"):
                    row.updated_at = now_iso()
        self._invalidate_caches(q)
        return _FakeUpdateResult(len(rows))

    async def bulk_update_by_id(self, updates_by_id: dict[str, dict], *, chunk_size: int = 1000) -> Any:
        """Update many rows by id, each with its OWN $set/$unset doc, in a
        bounded number of round trips instead of one update_one call per row.

        update_many (above) only helps when every matched row gets the SAME
        update_doc; the far more common batch-write shape in this app is "N
        different rows, each with its own new values" (reversing N different
        products' quantities, syncing N different ledger statuses, ...) — for
        that shape this is the primitive to use instead of a for-loop of
        update_one calls.

        updates_by_id: {row_id: {"$set": {...}} | {"$unset": {...}}, ...}
        Chunked at `chunk_size` ids per SELECT ... WHERE id IN (...) so a
        very large batch (thousands of rows) doesn't build one oversized
        IN-list statement or hold a single huge result set — each chunk is
        still one SELECT + N in-memory attribute sets flushed together by
        SQLAlchemy at the surrounding session's commit, not one UPDATE per
        row. Rows are all updated within ONE `get_session()` block (one
        transaction), matching update_many's atomicity — a failure partway
        through rolls back every change made so far in this call, not just
        the current chunk.

        Returns a _FakeUpdateResult with matched_count = rows actually found
        and updated (ids with no matching row are silently skipped, same as
        update_one's semantics for an unmatched filter).
        """
        Model = self._model()
        if Model is None or not updates_by_id:
            return _FakeUpdateResult(0)
        ids = list(updates_by_id.keys())
        matched = 0
        async with get_session() as session:
            for i in range(0, len(ids), chunk_size):
                chunk_ids = ids[i:i + chunk_size]
                stmt = select(Model).where(Model.id.in_(chunk_ids))
                tcond = _tenant_cond(Model)
                if tcond is not None:
                    stmt = stmt.where(tcond)
                result = await session.execute(stmt)
                rows = result.scalars().all()
                for row in rows:
                    _apply_set_update(row, updates_by_id[row.id])
                    if hasattr(row, "updated_at"):
                        row.updated_at = now_iso()
                matched += len(rows)
        self._invalidate_caches(None)
        return _FakeUpdateResult(matched)

    async def delete_one(self, q: dict) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeDeleteResult(0)
        async with get_session() as session:
            stmt = select(Model)
            conds = _conds_with_tenant(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row:
                await session.delete(row)
                self._invalidate_caches(q)
                return _FakeDeleteResult(1)
        return _FakeDeleteResult(0)

    async def delete_many(self, q: dict) -> Any:
        Model = self._model()
        if Model is None:
            return _FakeDeleteResult(0)
        async with get_session() as session:
            stmt = select(Model)
            conds = _conds_with_tenant(Model, q)
            if conds:
                stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            rows = result.scalars().all()
            count = 0
            for row in rows:
                await session.delete(row)
                count += 1
        self._invalidate_caches(q)
        return _FakeDeleteResult(count)

    async def count_documents(self, q: Optional[dict] = None) -> int:
        Model = self._model()
        if Model is None:
            return 0
        async with get_session() as session:
            stmt = select(func.count()).select_from(Model)
            conds = _conds_with_tenant(Model, q or {})
            if conds:
                stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            return result.scalar_one()

    def aggregate(self, pipeline: list) -> "MongoAggregateCursor":
        """Run a MongoDB-style aggregation pipeline.

        Returns a cursor (like motor/PyMongo) so existing call sites work
        unchanged in either idiom:

            docs = await db.coll.aggregate(pipeline).to_list(N)   # cursor style
            docs = await db.coll.aggregate(pipeline)              # direct await

        Strategy: load the rows the leading $match selects (pushed down to SQL
        via _to_filter), then execute the remaining stages in Python. This
        faithfully supports the operators this codebase actually uses —
        $match/$group/$sum/$avg/$min/$max/$first/$last/$push/$count/$sort/
        $limit/$skip/$unwind/$addFields/$project with $sum/$cond/$ifNull
        expressions — without a partial SQL translator that silently drops
        stages. Suitable for this app's report volumes (thousands of rows).
        """
        return MongoAggregateCursor(self._model(), list(pipeline or []))

    async def replace_one(self, q: dict, replacement: dict, upsert: bool = False) -> Any:
        return await self.update_one(q, replacement, upsert=upsert)

    async def distinct(self, field: str, q: Optional[dict] = None) -> list:
        Model = self._model()
        if Model is None:
            return []
        col = getattr(Model, field, None)
        if col is None:
            return []
        async with get_session() as session:
            stmt = select(col).distinct()
            conds = _conds_with_tenant(Model, q or {})
            if conds:
                stmt = stmt.where(and_(*conds))
            result = await session.execute(stmt)
            return [r for (r,) in result.all() if r is not None]

    async def create_index(self, *args, **kwargs):
        pass  # Indexes are handled by Alembic / create_all


class MongoFindBuilder:
    """Builder returned by collection.find() — supports .to_list(), .sort(), .skip(), .limit()."""

    def __init__(self, Model, q: dict, projection: Optional[dict] = None):
        self._Model = Model
        self._q = q
        self._projection = projection
        self._sort = []
        self._skip_n = 0
        self._limit_n = 0

    def sort(self, field_or_list, direction=None) -> MongoFindBuilder:
        if isinstance(field_or_list, list):
            self._sort = field_or_list
        else:
            self._sort = [(field_or_list, direction or 1)]
        return self

    def skip(self, n: int) -> MongoFindBuilder:
        self._skip_n = n
        return self

    def limit(self, n: int) -> MongoFindBuilder:
        self._limit_n = n
        return self

    async def to_list(self, length=None) -> list[dict]:
        if self._Model is None:
            return []
        async with get_session() as session:
            stmt = select(self._Model)
            conds = _conds_with_tenant(self._Model, self._q)
            if conds:
                stmt = stmt.where(and_(*conds))
            for field, direction in self._sort:
                col = getattr(self._Model, field, None)
                if col is None and hasattr(self._Model, "extra"):
                    col = self._Model.extra[field].astext
                elif col is None and hasattr(self._Model, "data"):
                    col = self._Model.data[field].astext
                if col is not None:
                    stmt = stmt.order_by(col.desc() if direction == -1 else col.asc())
            if self._skip_n:
                stmt = stmt.offset(self._skip_n)
            lim = length if length is not None else (self._limit_n or None)
            # Enforce hard cap — prevents accidental full-table scans from
            # to_list(50000) or to_list(1000000) calls in the routers.
            if lim is None or lim > _TO_LIST_HARD_CAP:
                lim = _TO_LIST_HARD_CAP
            stmt = stmt.limit(lim)
            result = await session.execute(stmt)
            rows = result.scalars().all()
        out = [d for r in rows if (d := _row_to_dict(r)) is not None]
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


class MongoAggregateCursor:
    """Cursor returned by collection.aggregate().

    Awaitable (``await cursor`` → full list) and supports ``.to_list(n)`` so
    both the ``await db.coll.aggregate(p).to_list(n)`` and ``await
    db.coll.aggregate(p)`` idioms work. The pipeline runs lazily on first await.
    """

    def __init__(self, Model, pipeline: list):
        self._Model = Model
        self._pipeline = pipeline

    async def _run(self) -> list[dict]:
        if self._Model is None:
            return []
        pipeline = list(self._pipeline)

        # Push a leading $match down to SQL so we don't load the whole table.
        sql_match = None
        if pipeline and "$match" in pipeline[0]:
            sql_match = pipeline[0]["$match"]
            pipeline = pipeline[1:]

        async with get_session() as session:
            stmt = select(self._Model)
            conds = _conds_with_tenant(self._Model, sql_match or {})
            if conds:
                stmt = stmt.where(and_(*conds))
            rows = (await session.execute(stmt)).scalars().all()
        docs: list[dict] = [d for d in (_row_to_dict(r) for r in rows) if d is not None]

        for stage in pipeline:
            docs = _agg_stage(stage, docs)
        return docs

    async def to_list(self, length=None) -> list[dict]:
        docs = await self._run()
        return docs if length is None else docs[:length]

    def __await__(self):
        return self._run().__await__()

    def __aiter__(self):
        return _AggIterator(self._run())


class _AggIterator:
    def __init__(self, coro):
        self._coro = coro
        self._rows = None

    async def __anext__(self):
        if self._rows is None:
            self._rows = iter(await self._coro)
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
        if "$divide" in expr:
            a, b = expr["$divide"]
            denom = _num(_eval_expr(b, doc))
            return _num(_eval_expr(a, doc)) / denom if denom else None
        if "$substr" in expr or "$substrBytes" in expr or "$substrCP" in expr:
            args = (expr.get("$substr") or expr.get("$substrBytes")
                    or expr.get("$substrCP") or [None, 0, 0])
            src, start, length = args
            s = _eval_expr(src, doc)
            s = "" if s is None else str(s)
            start = int(start)
            length = int(length)
            return s[start:start + length] if length >= 0 else s[start:]
        if "$concat" in expr:
            parts = []
            for o in expr["$concat"]:
                v = _eval_expr(o, doc)
                if v is None:
                    return None  # Mongo: $concat with any null → null
                parts.append(str(v))
            return "".join(parts)
        if "$toLower" in expr:
            v = _eval_expr(expr["$toLower"], doc)
            return str(v).lower() if v is not None else ""
        if "$toUpper" in expr:
            v = _eval_expr(expr["$toUpper"], doc)
            return str(v).upper() if v is not None else ""
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


def _is_expr_op(spec: dict) -> bool:
    """True if a dict is a single expression operator (e.g. {"$substr": [...]})
    rather than a document of grouping fields (e.g. {"year": "$y"})."""
    return len(spec) == 1 and next(iter(spec)).startswith("$")


def _eval_group_id(id_spec, doc: dict):
    """Evaluate a $group _id spec to its output value for one doc."""
    if isinstance(id_spec, str):
        return _eval_expr(id_spec, doc)
    if isinstance(id_spec, dict):
        if _is_expr_op(id_spec):
            return _eval_expr(id_spec, doc)
        return {k: _eval_expr(v, doc) for k, v in id_spec.items()}
    return id_spec


def _group_key(id_spec, doc: dict):
    """Compute the (hashable) _id key for a $group stage."""
    if id_spec is None:
        return None
    return _make_hashable(_eval_group_id(id_spec, doc))


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
            key = _group_key(id_spec, d)
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(d)
        out = []
        for key in order:
            bucket = buckets[key]
            # Reconstruct _id output (document, scalar expression, or None)
            _id_out = _eval_group_id(id_spec, bucket[0]) if id_spec is not None else None
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


class _CompatSession:
    """No-op client session. Postgres writes commit per-call through the compat
    layer, so multi-document transactions are not provided here; callers that
    open a session/transaction simply run their writes sequentially (matching
    the existing 'standalone Mongo' fallback path)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def start_transaction(self):
        return self


class _MongoClientCompat:
    """Stand-in for the Mongo client's session API."""

    async def start_session(self) -> _CompatSession:
        return _CompatSession()


class _MongoDBCompat:
    """Top-level `db` object. Attribute access returns a MongoCollectionCompat."""

    client = _MongoClientCompat()

    def __getattr__(self, name: str) -> MongoCollectionCompat:
        return MongoCollectionCompat(name)

    def __getitem__(self, name: str) -> MongoCollectionCompat:
        return MongoCollectionCompat(name)


# Exported singleton — all routers import this via `from core.db import db`
db = _MongoDBCompat()
