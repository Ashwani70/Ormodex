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
    core.db.db = db
    utils.db = db
    sl.db = db
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
