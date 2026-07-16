"""Integration test for the stock ledger posting service against an in-memory DB.

Proves the engine + DB layer compute the same closing value the pure unit tests
assert, through post_entry / on_hand — no live MongoDB or server needed.
"""
import asyncio

import core.db
import core.utils as utils
import core.stock_ledger as sl


# ── Minimal async Mongo fake supporting find().sort().to_list() + find_one ──

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, spec):
        # spec is a list of (field, direction) tuples
        for field, direction in reversed(spec):
            self._docs.sort(key=lambda d: d.get(field), reverse=(direction < 0))
        return self

    async def to_list(self, _n):
        return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc, session=None):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    def find(self, q=None, projection=None):
        q = q or {}
        matched = [d for d in self.docs if all(d.get(k) == v for k, v in q.items())]
        if projection and projection.get("_id") == 0:
            matched = [{k: v for k, v in d.items() if k != "_id"} for d in matched]
        return _Cursor(matched)

    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                out = dict(d)
                if projection and projection.get("_id") == 0:
                    out.pop("_id", None)
                return out
        return None


class _DB:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, _Collection())

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def _setup():
    db = _DB()
    core.db.db = db  # type: ignore[assignment]
    utils.db = db  # type: ignore[assignment]
    sl.db = db  # type: ignore[assignment]
    utils._txn_supported = False
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
GODOWN = "g1"


def _seed_item(db, method):
    asyncio.run(db.stock_items.insert_one(
        {"id": "item1", "name": "Widget", "valuation_method": method, "reorder_level": 5}
    ))


def _post(item, godown, qty, mtype, rate=None, dt=None):
    return asyncio.run(sl.post_entry(
        stock_item_id=item, godown_id=godown, qty=qty, movement_type=mtype,
        rate=rate, entry_date=dt, user=USER,
    ))


# Same mixed sequence as the pure unit tests: FIFO closing 300, WA closing 260.

def test_fifo_closing_value_through_db():
    db = _setup()
    _seed_item(db, "FIFO")
    _post("item1", GODOWN, 10, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", GODOWN, 10, "PURCHASE", rate=120, dt="2026-01-02")
    out1 = _post("item1", GODOWN, -15, "SALE", dt="2026-01-03")
    _post("item1", GODOWN, 5, "PURCHASE", rate=150, dt="2026-01-04")
    out2 = _post("item1", GODOWN, -8, "SALE", dt="2026-01-05")

    assert abs(out1["value"]) == 1600
    assert abs(out2["value"]) == 1050
    oh = asyncio.run(sl.on_hand("item1"))
    assert oh["qty"] == 2
    assert oh["value"] == 300


def test_weighted_avg_closing_value_through_db():
    db = _setup()
    _seed_item(db, "WEIGHTED_AVG")
    _post("item1", GODOWN, 10, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", GODOWN, 10, "PURCHASE", rate=120, dt="2026-01-02")
    out1 = _post("item1", GODOWN, -15, "SALE", dt="2026-01-03")
    _post("item1", GODOWN, 5, "PURCHASE", rate=150, dt="2026-01-04")
    out2 = _post("item1", GODOWN, -8, "SALE", dt="2026-01-05")

    assert abs(out1["value"]) == 1650   # 15 @ 110
    assert abs(out2["value"]) == 1040   # 8 @ 130
    oh = asyncio.run(sl.on_hand("item1"))
    assert oh["qty"] == 2
    assert oh["value"] == 260


def test_per_godown_fifo_layers_are_isolated():
    db = _setup()
    _seed_item(db, "FIFO")
    # Same item, two godowns at different costs.
    _post("item1", "gA", 10, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", "gB", 10, "PURCHASE", rate=200, dt="2026-01-02")
    # Outward from gB must consume gB's 200 layer, not gA's cheaper one.
    out = _post("item1", "gB", -4, "SALE", dt="2026-01-03")
    assert abs(out["value"]) == 800  # 4 @ 200

    oh_a = asyncio.run(sl.on_hand("item1", "gA"))
    oh_b = asyncio.run(sl.on_hand("item1", "gB"))
    assert oh_a["value"] == 1000
    assert oh_b["value"] == 1200  # 6 @ 200


# ── LIFO / Standard-cost / resolver through the DB layer ──

def test_lifo_closing_value_through_db():
    db = _setup()
    _seed_item(db, "LIFO")
    # Spec example: 100@100, 200@110, 150@130, then sell 220.
    _post("item1", GODOWN, 100, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", GODOWN, 200, "PURCHASE", rate=110, dt="2026-01-02")
    _post("item1", GODOWN, 150, "PURCHASE", rate=130, dt="2026-01-03")
    out = _post("item1", GODOWN, -220, "SALE", dt="2026-01-04")
    # LIFO consumes 150@130 + 70@110 = 27200.
    assert abs(out["value"]) == 27200
    oh = asyncio.run(sl.on_hand("item1"))
    assert oh["qty"] == 230
    assert oh["value"] == 100 * 100 + 130 * 110   # 24300
    assert oh["method"] == "LIFO"


def test_standard_cost_through_db():
    db = _setup()
    # standard_cost lives on the item row.
    asyncio.run(db.stock_items.insert_one(
        {"id": "item1", "name": "Widget",
         "valuation_method": "STANDARD_COST", "standard_cost": 105}
    ))
    _post("item1", GODOWN, 100, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", GODOWN, 50, "PURCHASE", rate=110, dt="2026-01-02")
    out = _post("item1", GODOWN, -30, "SALE", dt="2026-01-03")
    assert abs(out["value"]) == 30 * 105          # priced at standard, not actual
    oh = asyncio.run(sl.on_hand("item1"))
    assert oh["qty"] == 120
    assert oh["value"] == 120 * 105               # 12600
    assert oh["method"] == "STANDARD_COST"


def test_company_default_applies_when_item_has_no_override():
    db = _setup()
    # Item has NO valuation_method → must fall back to the company default (LIFO).
    asyncio.run(db.stock_items.insert_one({"id": "item1", "name": "Widget"}))
    asyncio.run(db.companies.insert_one(
        {"id": "c1", "extra": {"inventory_valuation_method": "LIFO"}}
    ))
    _post("item1", GODOWN, 100, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", GODOWN, 200, "PURCHASE", rate=110, dt="2026-01-02")
    _post("item1", GODOWN, 150, "PURCHASE", rate=130, dt="2026-01-03")
    out = _post("item1", GODOWN, -220, "SALE", dt="2026-01-04")
    assert abs(out["value"]) == 27200             # LIFO cost flow
    assert asyncio.run(sl.on_hand("item1"))["method"] == "LIFO"


def test_item_override_beats_company_default():
    db = _setup()
    # Company default LIFO, but the item overrides to FIFO — item wins.
    asyncio.run(db.stock_items.insert_one(
        {"id": "item1", "name": "Widget", "valuation_method": "FIFO"}
    ))
    asyncio.run(db.companies.insert_one(
        {"id": "c1", "extra": {"inventory_valuation_method": "LIFO"}}
    ))
    _post("item1", GODOWN, 100, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", GODOWN, 200, "PURCHASE", rate=110, dt="2026-01-02")
    _post("item1", GODOWN, 150, "PURCHASE", rate=130, dt="2026-01-03")
    out = _post("item1", GODOWN, -220, "SALE", dt="2026-01-04")
    assert abs(out["value"]) == 23200             # FIFO cost flow, not LIFO's 27200


# ── Stock Log dual-write mirror (Stock Log fix 2026-07-15) ──
#
# post_entry() must mirror every posting into stock_transactions, since that's
# the table the Stock Log grid, its summary cards, and its negative-stock
# count all read exclusively from — see core/stock_ledger.py's "Dual-write"
# docstring for the full story. These tests catch a regression where a v2
# posting flow (GRN, Purchase Return, Stock Adjustment, ...) becomes invisible
# to Stock Log again.

def test_post_entry_mirrors_into_stock_transactions():
    db = _setup()
    asyncio.run(db.stock_items.insert_one(
        {"id": "item1", "name": "Widget", "product_id": "prod1", "valuation_method": "FIFO"}
    ))
    entry = _post("item1", GODOWN, 50, "PURCHASE", rate=100, dt="2026-01-01")

    mirrored = db["stock_transactions"].docs
    assert len(mirrored) == 1
    row = mirrored[0]
    assert row["product_id"] == "prod1"          # resolved via stock_items link
    assert row["product_name"] == "Widget"
    assert row["godown_id"] == GODOWN
    assert row["delta"] == 50
    assert row["doc_type"] == "PURCHASE"
    assert row["rate"] == entry["rate"]
    assert row["value"] == entry["value"]


def test_post_entry_mirror_falls_back_when_item_unlinked_to_product():
    """A standalone v2 stock_items row (no product_id) must still get a
    usable mirror row — Stock Log should show the item's own name, not a blank."""
    db = _setup()
    asyncio.run(db.stock_items.insert_one(
        {"id": "item2", "name": "Standalone Item", "valuation_method": "WEIGHTED_AVG"}
    ))
    _post("item2", GODOWN, 10, "PURCHASE", rate=50, dt="2026-01-01")

    row = db["stock_transactions"].docs[0]
    assert row["product_id"] == "item2"           # falls back to stock_item_id
    assert row["product_name"] == "Standalone Item"


def test_post_entry_mirrors_outward_move_with_negative_delta():
    db = _setup()
    _seed_item(db, "WEIGHTED_AVG")
    _post("item1", GODOWN, 20, "PURCHASE", rate=100, dt="2026-01-01")
    _post("item1", GODOWN, -5, "SALE", dt="2026-01-02")

    rows = db["stock_transactions"].docs
    assert len(rows) == 2
    out_row = rows[1]
    assert out_row["delta"] == -5
    assert out_row["doc_type"] == "SALES"          # SALE movement_type -> SALES doc_type


def test_stock_transfer_posts_exactly_two_mirror_rows_no_double_write():
    """Regression guard: Stock Transfer used to hand-write its own mirror rows
    IN ADDITION to post_entry's; that would now double-post. Exactly one mirror
    row per post_entry call (two calls for a transfer: OUT + IN)."""
    db = _setup()
    _seed_item(db, "FIFO")
    _post("item1", "gA", 10, "PURCHASE", rate=100, dt="2026-01-01")
    out = _post("item1", "gA", -4, "TRANSFER_OUT", dt="2026-01-02")
    _post("item1", "gB", 4, "TRANSFER_IN", rate=out["rate"], dt="2026-01-02")

    rows = db["stock_transactions"].docs
    # 1 purchase + 1 transfer-out + 1 transfer-in = 3, never 4+ from double-mirroring.
    assert len(rows) == 3
    transfer_rows = [r for r in rows if r["doc_type"] == "STOCK_TRANSFER"]
    assert len(transfer_rows) == 2
    assert {r["delta"] for r in transfer_rows} == {-4, 4}


def test_mirror_failure_does_not_block_the_ledger_write():
    """The mirror is best-effort: if stock_transactions insert fails for any
    reason, stock_ledger_entries (the valuation source of truth) must still
    have been written — Stock Log visibility must never be able to break a
    stock posting."""
    db = _setup()
    _seed_item(db, "FIFO")

    class _BoomCollection(_Collection):
        async def insert_one(self, doc, session=None):
            raise RuntimeError("simulated stock_transactions outage")

    db._cols["stock_transactions"] = _BoomCollection()

    entry = _post("item1", GODOWN, 10, "PURCHASE", rate=100, dt="2026-01-01")
    assert entry["id"]  # post_entry returned normally despite the mirror failure
    oh = asyncio.run(sl.on_hand("item1"))
    assert oh["qty"] == 10 and oh["value"] == 1000  # ledger truth is intact
