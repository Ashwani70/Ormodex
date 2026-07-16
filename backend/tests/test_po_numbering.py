"""Tests for configurable Purchase Order numbering, uniqueness, locking & audit.

Runs against the real PostgreSQL/Supabase data layer (post-MongoDB migration).
The old in-memory fake ``db`` is gone: production CRUD (`crud_get`/`crud_create`)
executes through SQLAlchemy ``get_session()``, so the masters a PO references must
exist as real rows. Each test seeds its masters + resets the PO counter, then
cleans up everything it created so the shared DB is left untouched.
"""
import asyncio

import pytest
from fastapi import HTTPException

import core.po_numbering as pn
from core.db import db
from core.purchase_models import PurchaseOrderV2, POLine
from routers.purchase_v2 import create_order, update_order, order_number_audit


ADMIN = {"id": "admin1", "name": "Admin", "role": "admin"}
# A buyer with override+edit perms but not admin.
BUYER = {"id": "u2", "name": "Buyer", "role": "employee",
         "module_permissions": ["purchase", "po_number_override", "po_number_edit"]}
# A plain purchase user with no number perms.
PLAIN = {"id": "u3", "name": "Plain", "role": "employee",
         "module_permissions": ["purchase"]}

# Deterministic ids so cleanup is exact.
_VENDOR_ID = "test_pn_v1"
_ITEM_ID = "test_pn_i1"
_PO_COUNTER_KEY = f"{pn.PO_COLLECTION}_po_number_seq"
# PO numbers used by tests (so cleanup can target them precisely).
_TEST_PO_NUMBERS = {
    "PO-0100", "PO-0101", "MY-CUSTOM-1", "DUP-1", "PO-NEW-1", "PO-NEW-2",
    "PO-HACK", "PO0001", "PO-0001",
}


async def _seed_masters_async():
    """Upsert the vendor + stock item every test PO references."""
    await db.vendors.update_one(
        {"id": _VENDOR_ID},
        {"$set": {"id": _VENDOR_ID, "name": "Vendor 1", "state_code": "27"}},
        upsert=True,
    )
    await db.stock_items.update_one(
        {"id": _ITEM_ID},
        {"$set": {"id": _ITEM_ID, "name": "Item 1", "valuation_method": "WEIGHTED_AVG"}},
        upsert=True,
    )


async def _reset_counter_async():
    """Remove the global PO sequence counter so start_sequence is honoured fresh."""
    await db.counters.delete_one({"_id": _PO_COUNTER_KEY})


async def _cleanup_async(created_po_ids):
    """Delete every PO + audit row this test created, plus the seeded masters and
    counter, so the shared Supabase DB is left exactly as we found it."""
    for pid in created_po_ids:
        await db.po_number_audit.delete_many({"purchase_order_id": pid})
        await db.goods_receipt_notes_v2.delete_many({"purchase_order_id": pid})
        await db.purchase_orders_v2.delete_one({"id": pid})
    # Also sweep any POs left under our known test numbers (defensive).
    for num in _TEST_PO_NUMBERS:
        rows = await db.purchase_orders_v2.find({"po_number": num}).to_list(50)
        for r in rows:
            await db.po_number_audit.delete_many({"purchase_order_id": r["id"]})
            await db.purchase_orders_v2.delete_one({"id": r["id"]})
    await db.counters.delete_one({"_id": _PO_COUNTER_KEY})
    await db.vendors.delete_one({"id": _VENDOR_ID})
    await db.stock_items.delete_one({"id": _ITEM_ID})


@pytest.fixture
def pg(request):
    """Seed masters + reset counter before the test; clean up after.

    Exposes a list the test appends created PO ids to (so teardown can target
    them). Tests don't need to touch it directly — they use `_track()`.
    """
    created: list = []
    request._created_po_ids = created
    asyncio.run(_seed_masters_async())
    asyncio.run(_reset_counter_async())
    yield created
    asyncio.run(_cleanup_async(created))


def _create(payload, user, tracker):
    """Run create_order against real PG and remember the id for cleanup."""
    po = asyncio.run(create_order(payload, user=user))
    if po and po.get("id"):
        tracker.append(po["id"])
    return po


def _set_settings(**kw):
    s = {**pn.DEFAULT_SETTINGS, **kw, "id": "global"}
    asyncio.run(db.po_numbering_settings.update_one({"id": "global"}, {"$set": s}, upsert=True))


def _po_payload(po_number=None, reason=None):
    return PurchaseOrderV2(
        po_number=po_number,
        po_number_reason=reason,
        vendor_id=_VENDOR_ID,
        lines=[POLine(stock_item_id=_ITEM_ID, qty=5.0, rate=100.0, gst_rate=18.0)],
    )


# ───────────────────────── Format builder (pure — no DB) ─────────────────────

def test_build_number_matches_spec_examples():
    assert pn.build_po_number(
        {"prefix": "PO", "fy_format": "26-27", "branch_code": "", "separator": "/", "sequence_length": 4}, 1
    ) == "PO/26-27/0001"
    assert pn.build_po_number(
        {"prefix": "PO", "fy_format": "", "branch_code": "DEL", "separator": "-", "sequence_length": 5}, 1
    ) == "DEL-PO-00001"
    assert pn.build_po_number(
        {"prefix": "PO", "fy_format": "2026", "branch_code": "", "separator": "-", "sequence_length": 6}, 123
    ) == "PO-2026-000123"


def test_build_number_no_separator():
    assert pn.build_po_number(
        {"prefix": "PO", "fy_format": "", "branch_code": "", "separator": "", "sequence_length": 5}, 7
    ) == "PO00007"


# ───────────────────────── Auto generate ─────────────────────────

def test_auto_generate_uses_start_sequence_and_increments(pg):
    _set_settings(mode="AUTO", prefix="PO", separator="-", start_sequence=100, sequence_length=4)

    po1 = _create(_po_payload(), ADMIN, pg)
    po2 = _create(_po_payload(), ADMIN, pg)
    assert po1["po_number"] == "PO-0100"
    assert po2["po_number"] == "PO-0101"
    assert po1["po_number_locked"] is False


# ───────────────────────── Manual entry + permissions ─────────────────────────

def test_manual_mode_requires_number(pg):
    _set_settings(mode="MANUAL")
    with pytest.raises(HTTPException) as exc:
        _create(_po_payload(po_number=None), ADMIN, pg)
    assert exc.value.status_code == 400
    assert "required" in exc.value.detail.lower()


def test_manual_number_blocked_without_override_permission(pg):
    _set_settings(mode="AUTO")
    with pytest.raises(HTTPException) as exc:
        _create(_po_payload(po_number="MY-CUSTOM-1"), PLAIN, pg)
    assert exc.value.status_code == 403
    assert "po_number_override" in exc.value.detail


def test_manual_number_allowed_with_override_permission_and_audited(pg):
    _set_settings(mode="MANUAL")
    po = _create(_po_payload(po_number="MY-CUSTOM-1", reason="client ref"), BUYER, pg)
    assert po["po_number"] == "MY-CUSTOM-1"
    audit = asyncio.run(order_number_audit(po["id"], user=BUYER))
    assert len(audit) == 1
    assert audit[0]["new_po_number"] == "MY-CUSTOM-1"
    assert audit[0]["old_po_number"] is None
    assert audit[0]["reason"] == "client ref"


# ───────────────────────── Uniqueness ─────────────────────────

def test_duplicate_manual_number_rejected(pg):
    _set_settings(mode="MANUAL")
    _create(_po_payload(po_number="DUP-1"), BUYER, pg)
    with pytest.raises(HTTPException) as exc:
        _create(_po_payload(po_number="DUP-1"), BUYER, pg)
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


# ───────────────────────── Edit rules + lock ─────────────────────────

def test_edit_number_on_draft_with_permission_audited(pg):
    _set_settings(mode="AUTO", prefix="PO", start_sequence=1, sequence_length=4)
    po = _create(_po_payload(), ADMIN, pg)
    old = po["po_number"]

    edit = _po_payload(po_number="PO-NEW-1", reason="typo fix")
    updated = asyncio.run(update_order(po["id"], edit, user=BUYER))
    assert updated["po_number"] == "PO-NEW-1"

    audit = asyncio.run(order_number_audit(po["id"], user=BUYER))
    assert audit[0]["old_po_number"] == old
    assert audit[0]["new_po_number"] == "PO-NEW-1"
    assert audit[0]["reason"] == "typo fix"


def test_edit_number_blocked_without_edit_permission(pg):
    _set_settings(mode="AUTO")
    po = _create(_po_payload(), ADMIN, pg)
    edit = _po_payload(po_number="PO-NEW-2")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_order(po["id"], edit, user=PLAIN))
    assert exc.value.status_code == 403
    assert "po_number_edit" in exc.value.detail


def test_number_locked_once_sent(pg):
    _set_settings(mode="AUTO")
    po = _create(_po_payload(), ADMIN, pg)
    # Move the PO out of Draft.
    asyncio.run(db.purchase_orders_v2.update_one({"id": po["id"]}, {"$set": {"status": "SENT"}}))

    edit = _po_payload(po_number="PO-HACK")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_order(po["id"], edit, user=BUYER))
    assert exc.value.status_code == 400
    assert "locked" in exc.value.detail.lower()


def test_number_locked_when_grn_exists(pg):
    _set_settings(mode="AUTO")
    po = _create(_po_payload(), ADMIN, pg)
    asyncio.run(db.goods_receipt_notes_v2.insert_one(
        {"id": f"grn_{po['id']}", "purchase_order_id": po["id"]}))
    assert asyncio.run(pn.compute_locked({**po, "id": po["id"]})) is True


def test_editing_same_number_is_noop_not_audited(pg):
    _set_settings(mode="AUTO")
    po = _create(_po_payload(), ADMIN, pg)
    # Re-submit with the same number — should not require perms or create audit.
    edit = _po_payload(po_number=po["po_number"])
    asyncio.run(update_order(po["id"], edit, user=PLAIN))
    audit = asyncio.run(order_number_audit(po["id"], user=ADMIN))
    assert audit == []
