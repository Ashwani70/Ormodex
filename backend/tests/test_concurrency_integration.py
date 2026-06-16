"""Real-DB concurrency integration tests (live MongoDB required).

These exercise the duplicate-movement guarantee against an actual MongoDB —
not the in-memory fake — by firing genuinely concurrent inserts and relying on
the unique index `uniq_voucher_stock_movement` to reject duplicates.

Skips cleanly when no MongoDB is reachable (e.g. CI without a DB), so it never
breaks the unit suite. Uses a throwaway database that is dropped on teardown.

KNOWN GAP (documented, not demonstrated): true write+audit *transactional
rollback* needs a replica set (multi-document transactions). The local server is
typically standalone, so that path is covered by the app-level compensating
logic + this index, not by a server transaction. If a replica set is available
these same inserts would additionally roll back atomically.
"""
import asyncio
import os
import uuid

import pytest

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo.errors import DuplicateKeyError
    _MOTOR = True
except Exception:  # pragma: no cover
    _MOTOR = False

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


def _mongo_available() -> bool:
    if not _MOTOR:
        return False
    async def _check():
        c = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=1500)
        try:
            await c.admin.command("ping")
            return True
        except Exception:
            return False
        finally:
            c.close()
    try:
        return asyncio.get_event_loop().run_until_complete(_check())
    except RuntimeError:
        return asyncio.run(_check())


pytestmark = pytest.mark.skipif(not _mongo_available(),
                                reason="No MongoDB reachable at MONGO_URL — integration test skipped")


def _movement(src_id, item="I1"):
    """A stock-movement doc keyed exactly like core posting produces."""
    return {
        "id": str(uuid.uuid4()),
        "source_doc_type": "voucher", "source_doc_id": src_id,
        "stock_item_id": item, "movement_type": "PURCHASE_IN",
        "batch_id": None, "serial_id": None,
        "qty": 10.0, "rate": 5.0, "value": 50.0,
    }


async def _with_db(coro):
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=2000)
    dbname = f"gw_test_{uuid.uuid4().hex[:10]}"
    db = client[dbname]
    try:
        return await coro(db)
    finally:
        await client.drop_database(dbname)
        client.close()


def test_unique_index_blocks_concurrent_duplicate_movements():
    """Fire N concurrent inserts of the SAME movement key; exactly one survives."""
    async def run(db):
        coll = db["stock_ledger_entries"]
        await coll.create_index(
            [("source_doc_type", 1), ("source_doc_id", 1), ("stock_item_id", 1),
             ("movement_type", 1), ("batch_id", 1), ("serial_id", 1)],
            unique=True,
            partialFilterExpression={"source_doc_type": "voucher"},
            name="uniq_voucher_stock_movement",
        )

        async def try_insert():
            try:
                await coll.insert_one(_movement("V1"))
                return "ok"
            except DuplicateKeyError:
                return "dup"

        # 20 genuinely concurrent attempts at the same logical movement.
        results = await asyncio.gather(*[try_insert() for _ in range(20)])
        survived = await coll.count_documents({"source_doc_id": "V1"})
        assert survived == 1, f"expected exactly 1 movement, found {survived}"
        assert results.count("ok") == 1
        assert results.count("dup") == 19

    asyncio.run(_with_db(run))


def test_distinct_sources_all_insert():
    """Different source docs are distinct movements — all should persist."""
    async def run(db):
        coll = db["stock_ledger_entries"]
        await coll.create_index(
            [("source_doc_type", 1), ("source_doc_id", 1), ("stock_item_id", 1),
             ("movement_type", 1), ("batch_id", 1), ("serial_id", 1)],
            unique=True,
            partialFilterExpression={"source_doc_type": "voucher"},
            name="uniq_voucher_stock_movement",
        )
        await asyncio.gather(*[coll.insert_one(_movement(f"V{i}")) for i in range(10)])
        assert await coll.count_documents({"source_doc_type": "voucher"}) == 10

    asyncio.run(_with_db(run))


def test_concurrent_posts_via_engine_against_real_db():
    """End-to-end: post the same voucher concurrently through the engine against a
    real DB; the index guarantees a single movement even if the app-level check
    races."""
    import core.db
    import core.utils as utils
    import core.voucher_engine as ve
    import core.stock_ledger as sl

    async def run(db):
        core.db.db = db; utils.db = db; ve.db = db; sl.db = db
        await db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True})
        await db.stock_items.insert_one(
            {"id": "I1", "tenant_id": "t1", "is_deleted": False, "valuation_method": "WEIGHTED_AVG"})
        await db["stock_ledger_entries"].create_index(
            [("source_doc_type", 1), ("source_doc_id", 1), ("stock_item_id", 1),
             ("movement_type", 1), ("batch_id", 1), ("serial_id", 1)],
            unique=True, partialFilterExpression={"source_doc_type": "voucher"},
            name="uniq_voucher_stock_movement")

        v = {"id": "GRN1", "tenant_id": "t1", "is_deleted": False, "status": "approved",
             "parent_type": "receipt_note", "voucher_no": "GRN1", "date": "2026-06-01",
             "inventory_lines": [{"stock_item_id": "I1", "location_id": "W", "qty": 10, "rate": 5}],
             "links": [], "statutory": None}
        await db.vouchers_v2.insert_one(v)

        user = {"id": "u1", "name": "T", "role": "admin"}
        # Concurrent posts of the same voucher. The unique index ensures at most
        # one movement persists; duplicate-key errors from the loser(s) are the
        # mechanism (some attempts may surface as exceptions — that's expected).
        async def attempt():
            try:
                return await ve.post_voucher(v, user, "t1")
            except DuplicateKeyError:
                return {"posted": True, "raced": True}
        await asyncio.gather(*[attempt() for _ in range(8)], return_exceptions=True)

        movements = await db["stock_ledger_entries"].count_documents({"source_doc_id": "GRN1"})
        assert movements == 1, f"expected 1 movement, found {movements}"

    asyncio.run(_with_db(run))
