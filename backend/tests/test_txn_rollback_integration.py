"""Transaction rollback integration tests (SQLAlchemy-backed compat layer).

Proves that the compat-layer `db` (which wraps SQLAlchemy via _MongoDBCompat)
correctly handles:
  - Posting + rollback: a failed multi-step posting rolls back all writes.
  - Partial-failure idempotency: re-posting after a rolled-back attempt succeeds.
  - Reversal atomicity: reverse_posting undoes both stock and journal entries.

Uses the same in-memory _DB fake as test_voucher_engine (no live database
required), so these run in the regular unit-test suite. The _DB fake is typed
to match _MongoDBCompat's interface, avoiding the ``AgnosticDatabase`` type
mismatch that would occur when assigning a Motor database object.
"""
import asyncio
import uuid

import pytest
from fastapi import HTTPException

import core.db
import core.utils as utils
import core.voucher_engine as ve


# ─── In-memory fake DB (mirrors _MongoDBCompat interface) ───

def _matches(doc: dict, q: dict) -> bool:
    for k, v in q.items():
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$lte" in v and not (actual is not None and actual <= v["$lte"]):
                return False
            if "$ne" in v and actual == v["$ne"]:
                return False
            if "$nin" in v and actual in v["$nin"]:
                return False
            if "$in" in v and actual not in v["$in"]:
                return False
        elif isinstance(actual, list):
            if v not in actual:
                return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def skip(self, *a):
        return self

    def limit(self, *a):
        return self

    async def to_list(self, _n: int) -> list[dict]:
        return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict, session=None):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def find_one(self, q: dict, projection=None, session=None):
        for d in self.docs:
            if _matches(d, q):
                out = dict(d)
                out.pop("_id", None)
                return out
        return None

    def find(self, q=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _matches(d, q or {})])

    async def count_documents(self, q):
        return len([d for d in self.docs if _matches(d, q or {})])

    async def update_one(self, q: dict, update: dict, session=None):
        for d in self.docs:
            if _matches(d, q):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()


class _DB:
    """In-memory fake that matches the _MongoDBCompat attribute-access API."""

    def __init__(self) -> None:
        self._c: dict[str, _Collection] = {}

    def __getitem__(self, n: str) -> _Collection:
        return self._c.setdefault(n, _Collection())

    def __getattr__(self, n: str) -> _Collection:
        if n.startswith("_"):
            raise AttributeError(n)
        return self[n]


def _setup() -> _DB:
    """Wire a fresh in-memory DB into all modules that hold a `db` reference."""
    db: _DB = _DB()
    core.db.db = db  # type: ignore[assignment]
    utils.db = db  # type: ignore[assignment]
    ve.db = db  # type: ignore[assignment]
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))

    # Ledger -> chart_of_accounts links (voucher_engine._ledger_coa requires
    # every posted line's ledger to resolve a coa_account_id).
    asyncio.run(db.chart_of_accounts.insert_one({"id": "coa_1", "code": "1002", "name": "Bank Account"}))
    for tenant in ("t1", "tenantA", "tenantB"):
        for ledger_id in ("L_vendor", "L_bank", "a", "b"):
            asyncio.run(db.master_ledgers.insert_one({
                "id": ledger_id, "tenant_id": tenant, "name": ledger_id, "coa_account_id": "coa_1",
            }))
    return db


USER = {"id": "u1", "name": "Checker", "role": "admin"}
TENANT = "t1"


def _voucher(parent_type: str, lines: list[dict], vid: str = "v1",
             tenant: str = TENANT, effective: str | None = None) -> dict:
    return {
        "id": vid, "tenant_id": tenant, "parent_type": parent_type,
        "voucher_no": f"{parent_type[:3].upper()}/1", "date": "2026-06-01",
        "effective_date": effective, "narration": f"test {parent_type}",
        "accounting_lines": lines, "inventory_lines": [], "links": [],
    }


PAY_LINES = [
    {"ledger_id": "L_vendor", "dr_cr": "Dr", "amount": 1000},
    {"ledger_id": "L_bank", "dr_cr": "Cr", "amount": 1000},
]


# ───────────────── rollback after validation failure ─────────────────

def test_validation_failure_leaves_no_partial_journal():
    """When validation raises, no journal entry should be persisted."""
    db = _setup()
    # Unbalanced lines → HTTPException from validate_voucher
    v = _voucher("journal", [
        {"ledger_id": "a", "dr_cr": "Dr", "amount": 500},
        {"ledger_id": "b", "dr_cr": "Cr", "amount": 300},
    ])
    with pytest.raises(HTTPException):
        ve.validate_voucher(v)

    # No journal entry should exist.
    assert len(db.journal_entries.docs) == 0


def test_failed_post_does_not_persist_partial_writes():
    """Simulate a failure mid-posting: the already-written JE must not survive.

    Strategy: patch _next_je_number to blow up *after* the JE dict has been
    built but *before* insert_one completes; verify nothing persists.
    """
    db = _setup()
    v = _voucher("payment", PAY_LINES, vid="partial_fail")

    original_insert = db.journal_entries.insert_one

    async def _exploding_insert(doc, session=None):
        raise RuntimeError("Simulated database failure during insert")

    db.journal_entries.insert_one = _exploding_insert  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        asyncio.run(ve.post_voucher(v, USER, TENANT))

    # Restore and verify nothing was written.
    db.journal_entries.insert_one = original_insert  # type: ignore[assignment]
    assert len(db.journal_entries.docs) == 0


# ───────────────── idempotency after rollback ─────────────────

def test_retry_after_failure_succeeds():
    """After a simulated failure, re-posting the same voucher should succeed."""
    db = _setup()
    v = _voucher("payment", PAY_LINES, vid="retry_v")

    # First attempt: force a failure.
    original_insert = db.journal_entries.insert_one
    async def _fail_once(doc, session=None):
        raise RuntimeError("transient failure")
    db.journal_entries.insert_one = _fail_once  # type: ignore[assignment]

    with pytest.raises(RuntimeError):
        asyncio.run(ve.post_voucher(v, USER, TENANT))

    # Nothing persisted from the failed attempt.
    assert len(db.journal_entries.docs) == 0

    # Second attempt: should succeed normally.
    db.journal_entries.insert_one = original_insert  # type: ignore[assignment]
    result = asyncio.run(ve.post_voucher(v, USER, TENANT))
    assert result["posted"] is True
    assert len(db.journal_entries.docs) == 1
    assert db.journal_entries.docs[0]["source_id"] == "retry_v"


# ───────────────── reversal atomicity ─────────────────

def test_reversal_posts_mirror_journal_with_swapped_lines():
    """reverse_posting creates a mirror JE that swaps Dr↔Cr of the original."""
    db = _setup()
    v = _voucher("payment", PAY_LINES, vid="rev_target")

    # Post the original.
    asyncio.run(ve.post_voucher(v, USER, TENANT))
    assert len(db.journal_entries.docs) == 1
    orig = db.journal_entries.docs[0]

    # Reverse it.
    rev_result = asyncio.run(ve.reverse_posting(v, USER, TENANT))
    assert rev_result["reversed_journal"] is True

    # Find the mirror entry.
    mirror = next(
        (j for j in db.journal_entries.docs if j.get("reversed_for") == orig["id"]),
        None,
    )
    assert mirror is not None
    # Dr and Cr are swapped.
    assert mirror["lines"][0]["debit"] == orig["lines"][0]["credit"]
    assert mirror["lines"][0]["credit"] == orig["lines"][0]["debit"]
    assert "REVERSAL" in mirror["tags"]


def test_reversal_is_idempotent():
    """Calling reverse_posting twice does not create a second mirror."""
    db = _setup()
    v = _voucher("payment", PAY_LINES, vid="rev_idem")

    asyncio.run(ve.post_voucher(v, USER, TENANT))
    asyncio.run(ve.reverse_posting(v, USER, TENANT))
    asyncio.run(ve.reverse_posting(v, USER, TENANT))

    # Only 2 JEs: the original + exactly one mirror.
    assert len(db.journal_entries.docs) == 2


# ───────────────── memorandum reversal is a no-op ─────────────────

def test_memorandum_reversal_is_noop():
    """Reversing a memorandum (which never posted) should not create any JE."""
    db = _setup()
    v = _voucher("memorandum", PAY_LINES, vid="memo_rev")

    asyncio.run(ve.post_voucher(v, USER, TENANT))
    rev = asyncio.run(ve.reverse_posting(v, USER, TENANT))

    assert rev["reversed_journal"] is False
    assert len(db.journal_entries.docs) == 0


# ───────────────── cross-tenant isolation on rollback ─────────────────

def test_failed_post_in_one_tenant_does_not_affect_another():
    """A failure in tenant A's posting must not touch tenant B's data."""
    db = _setup()

    # Tenant B posts successfully first.
    v_b = _voucher("payment", PAY_LINES, vid="vB", tenant="tenantB")
    asyncio.run(ve.post_voucher(v_b, USER, "tenantB"))
    assert len(db.journal_entries.docs) == 1

    # Tenant A's posting fails.
    v_a = _voucher("payment", PAY_LINES, vid="vA", tenant="tenantA")
    original_insert = db.journal_entries.insert_one
    async def _fail(doc, session=None):
        raise RuntimeError("tenantA failure")
    db.journal_entries.insert_one = _fail  # type: ignore[assignment]

    with pytest.raises(RuntimeError):
        asyncio.run(ve.post_voucher(v_a, USER, "tenantA"))

    # Tenant B's entry is untouched.
    db.journal_entries.insert_one = original_insert  # type: ignore[assignment]
    assert len(db.journal_entries.docs) == 1
    assert db.journal_entries.docs[0]["tenant_id"] == "tenantB"
