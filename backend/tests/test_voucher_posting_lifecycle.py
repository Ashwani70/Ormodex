"""Document posting lifecycle: inventory movements, vouchers, reversal, recon.

Drives the voucher engine + stock ledger against an in-memory fake DB. Covers
the operational flow end-to-end:
  - approved order + posted delivery/receipt → stock movement + (for accounting
    types) a journal entry, with a doc→voucher reference
  - partial fulfilment / backorder
  - reversal posts opposite movements + reversing JE (idempotent)
  - concurrent / repeated posting is idempotent (no duplicate movements)
  - job work issue → receipt → reconciliation (posted-only)
  - inventory valuation reflects only posted movements
"""
import asyncio

import core.db
import core.utils as utils
import core.voucher_engine as ve
import core.stock_ledger as sl


def _get(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, list):
            return [(_get(x, part) if isinstance(x, dict) else None) for x in cur]
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _match(doc, q):
    for k, v in q.items():
        if "." in k:
            actual = _get(doc, k)
            if isinstance(actual, list):
                if v not in actual:
                    return False
                continue
            if actual != v:
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$lte" in v and not (actual is not None and actual <= v["$lte"]): return False
            if "$gte" in v and not (actual is not None and actual >= v["$gte"]): return False
            if "$ne" in v and actual == v["$ne"]: return False
            if "$nin" in v:
                vals = actual if isinstance(actual, list) else [actual]
                if any(x in v["$nin"] for x in vals): return False
        elif isinstance(actual, list):
            if v not in actual: return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a, **k): return self
    def skip(self, *a): return self
    def limit(self, *a): return self
    async def to_list(self, _n): return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self): self.docs = []
    async def insert_one(self, doc, session=None):
        self.docs.append(dict(doc)); return type("R", (), {"inserted_id": doc.get("id")})()
    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if _match(d, q):
                out = dict(d); out.pop("_id", None); return out
        return None
    def find(self, q=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _match(d, q or {})])
    async def count_documents(self, q):
        return len([d for d in self.docs if _match(d, q or {})])
    async def update_one(self, q, update, session=None, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(update.get("$set", {})); return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()
    async def create_index(self, *a, **k): return "idx"


class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Collection())
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        return self[n]


def _setup():
    db = _DB()
    core.db.db = db; utils.db = db; ve.db = db; sl.db = db
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    # Stock item with a known valuation method (weighted avg).
    asyncio.run(db.stock_items.insert_one(
        {"id": "I1", "tenant_id": "t1", "is_deleted": False, "valuation_method": "WEIGHTED_AVG"}))
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
T = "t1"


def _voucher(db, vid, parent_type, inv_lines, *, acct_lines=None, links=None, statutory=None, status="approved"):
    doc = {
        "id": vid, "tenant_id": T, "is_deleted": False, "status": status,
        "parent_type": parent_type, "voucher_no": vid, "date": "2026-06-01",
        "inventory_lines": inv_lines, "accounting_lines": acct_lines or [],
        "links": links or [], "statutory": statutory,
    }
    asyncio.run(db.vouchers_v2.insert_one(doc))
    return doc


def _onhand(item="I1"):
    return asyncio.run(sl.on_hand(item))


# ───────────────────── receipt → stock in ; dispatch → stock out ─────────────────────

def test_receipt_note_posts_stock_in():
    db = _setup()
    v = _voucher(db, "GRN1", "receipt_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 100, "rate": 50}])
    res = asyncio.run(ve.post_voucher(v, USER, T))
    assert res["posted"] and res["movements"] == 1
    oh = _onhand()
    assert oh["qty"] == 100 and oh["value"] == 5000


def test_delivery_note_posts_stock_out():
    db = _setup()
    _voucher(db, "GRN1", "receipt_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 100, "rate": 50}])
    asyncio.run(ve.post_voucher({"id": "GRN1", "parent_type": "receipt_note", "date": "2026-06-01",
                                 "inventory_lines": [{"stock_item_id": "I1", "location_id": "G1", "qty": 100, "rate": 50}]},
                                USER, T))
    v = _voucher(db, "DN1", "delivery_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 30}])
    asyncio.run(ve.post_voucher(v, USER, T))
    oh = _onhand()
    assert oh["qty"] == 70   # 100 in, 30 out


# ───────────────────── idempotency / concurrency ─────────────────────

def test_repeated_post_is_idempotent_no_duplicate_movements():
    db = _setup()
    v = _voucher(db, "GRN1", "receipt_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 100, "rate": 50}])
    asyncio.run(ve.post_voucher(v, USER, T))
    again = asyncio.run(ve.post_voucher(v, USER, T))    # simulate re-approve / retry
    assert again["posted"] is True and again.get("already_posted") is True
    # Only one movement exists despite two post calls.
    assert len(db.stock_ledger_entries.docs) == 1
    assert _onhand()["qty"] == 100


def test_concurrent_posts_serialized_produce_single_movement():
    db = _setup()
    v = _voucher(db, "GRN1", "receipt_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 10, "rate": 5}])

    async def race():
        # Two coroutines try to post the same voucher; the dedup guard means the
        # net effect is a single movement.
        await ve.post_voucher(v, USER, T)
        await ve.post_voucher(v, USER, T)
    asyncio.run(race())
    assert len([d for d in db.stock_ledger_entries.docs if d["source_doc_id"] == "GRN1"]) == 1


# ───────────────────── reversal ─────────────────────

def test_reversal_posts_opposite_movement_and_is_idempotent():
    db = _setup()
    v = _voucher(db, "GRN1", "receipt_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 100, "rate": 50}])
    asyncio.run(ve.post_voucher(v, USER, T))
    assert _onhand()["qty"] == 100

    r1 = asyncio.run(ve.reverse_posting(v, USER, T))
    assert r1["reversed_stock"] == 1
    assert _onhand()["qty"] == 0          # netted back out

    r2 = asyncio.run(ve.reverse_posting(v, USER, T))   # idempotent
    assert r2["reversed_stock"] == 0
    assert _onhand()["qty"] == 0


def test_reversal_of_accounting_voucher_mirrors_journal():
    db = _setup()
    v = _voucher(db, "PAY1", "payment", [], acct_lines=[
        {"ledger_id": "L_v", "dr_cr": "Dr", "amount": 1000},
        {"ledger_id": "L_b", "dr_cr": "Cr", "amount": 1000},
    ])
    asyncio.run(ve.post_voucher(v, USER, T))
    assert len([j for j in db.journal_entries.docs if j["source_id"] == "PAY1"]) == 1
    res = asyncio.run(ve.reverse_posting(v, USER, T))
    assert res["reversed_journal"] is True
    # Now two entries for the source: original + reversal mirror.
    entries = [j for j in db.journal_entries.docs if j["source_id"] == "PAY1"]
    assert len(entries) == 2
    mirror = next(j for j in entries if "REVERSAL" in j.get("tags", []))
    assert mirror["lines"][0]["credit"] == 1000   # Dr→Cr swapped


# ───────────────────── job work issue → receipt → reconciliation ─────────────────────

def test_job_work_issue_receipt_reconciliation():
    db = _setup()
    # Issue 50 to job worker (WIP out).
    jc = _voucher(db, "JC1", "job_work_challan",
                  [{"stock_item_id": "I1", "location_id": "G1", "qty": 50, "rate": 10}],
                  statutory={"extra": {"goods_type": "inputs"}}, status="posted")
    asyncio.run(ve.post_voucher(jc, USER, T))
    # Receive 50 back (WIP/FG in), linked to the challan.
    mi = _voucher(db, "MI1", "job_work_material_inward",
                  [{"stock_item_id": "I1", "location_id": "G1", "qty": 50, "rate": 10}],
                  links=[{"ref_voucher_id": "JC1", "ref_type": "job_work_challan"}], status="posted")
    asyncio.run(ve.post_voucher(mi, USER, T))

    recon = asyncio.run(ve.job_work_reconciliation(T, as_of="2026-06-16"))
    ch = next(c for c in recon["challans"] if c["challan_id"] == "JC1")
    assert ch["total_pending_qty"] == 0 and ch["alert"] == "closed"


def test_job_work_reconciliation_ignores_unposted():
    db = _setup()
    # Challan only approved (not posted) → reconciliation must not see it.
    _voucher(db, "JC2", "job_work_challan",
             [{"stock_item_id": "I1", "qty": 5}],
             statutory={"extra": {"goods_type": "inputs"}}, status="approved")
    recon = asyncio.run(ve.job_work_reconciliation(T, as_of="2026-06-16"))
    assert all(c["challan_id"] != "JC2" for c in recon["challans"])


# ───────────────────── order → fulfilment / backorder ─────────────────────

def test_partial_fulfilment_and_backorder():
    db = _setup()
    _voucher(db, "SO1", "sales_order", [{"stock_item_id": "I1", "qty": 100}], status="approved")
    # Posted delivery for 40 against the SO.
    _voucher(db, "DN1", "delivery_note", [{"stock_item_id": "I1", "qty": 40}],
             links=[{"ref_voucher_id": "SO1", "ref_type": "sales_order"}], status="posted")
    ff = asyncio.run(ve.order_fulfilment("SO1", T))
    row = ff["lines"][0]
    assert row["fulfilled_qty"] == 40 and row["pending_qty"] == 60
    assert row["backorder_qty"] == 60 and ff["has_backorder"] is True
    assert ff["fully_fulfilled"] is False


def test_fulfilment_ignores_unposted_deliveries():
    db = _setup()
    _voucher(db, "SO1", "sales_order", [{"stock_item_id": "I1", "qty": 10}], status="approved")
    # Delivery only approved, not posted → does not count toward fulfilment.
    _voucher(db, "DN1", "delivery_note", [{"stock_item_id": "I1", "qty": 10}],
             links=[{"ref_voucher_id": "SO1", "ref_type": "sales_order"}], status="approved")
    ff = asyncio.run(ve.order_fulfilment("SO1", T))
    assert ff["lines"][0]["fulfilled_qty"] == 0 and ff["has_backorder"] is True


# ───────────────────── valuation after posting ─────────────────────

def test_valuation_uses_posted_movements_only():
    db = _setup()
    # Two receipts at different rates → weighted average.
    v1 = _voucher(db, "G1", "receipt_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 10, "rate": 100}])
    asyncio.run(ve.post_voucher(v1, USER, T))
    v2 = _voucher(db, "G2", "receipt_note", [{"stock_item_id": "I1", "location_id": "G1", "qty": 10, "rate": 120}])
    asyncio.run(ve.post_voucher(v2, USER, T))
    oh = _onhand()
    assert oh["qty"] == 20 and oh["value"] == 2200   # 10*100 + 10*120
    # A draft (never posted) receipt must not affect valuation: post nothing.
    _voucher(db, "G3", "receipt_note", [{"stock_item_id": "I1", "qty": 5, "rate": 999}], status="draft")
    assert _onhand()["value"] == 2200
