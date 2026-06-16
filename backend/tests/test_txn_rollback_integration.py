"""Transactional write+audit rollback — requires a MongoDB REPLICA SET.

The app's core.utils._write_with_audit wraps the business write and its audit
record in a multi-document transaction *when the server supports it*. On a
standalone mongod that path can't run, so this proves the atomic-rollback
guarantee that the unit suite (in-memory fake) and the standalone concurrency
test cannot:

  if the audit insert fails inside the transaction, the business write is rolled
  back — no orphaned, un-audited document.

Skips cleanly unless MONGO_URL points at a replica set. Spin one up with
docker-compose.mongo-rs.yml, then:
    export MONGO_URL="mongodb://localhost:27017/?replicaSet=rs0"
"""
import asyncio
import os
import uuid

import pytest

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    _MOTOR = True
except Exception:  # pragma: no cover
    _MOTOR = False

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


def _is_replica_set() -> bool:
    if not _MOTOR:
        return False
    async def _check():
        c = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=1500)
        try:
            hello = await c.admin.command("hello")
            return bool(hello.get("setName"))
        except Exception:
            return False
        finally:
            c.close()
    try:
        return asyncio.get_event_loop().run_until_complete(_check())
    except RuntimeError:
        return asyncio.run(_check())


pytestmark = pytest.mark.skipif(
    not _is_replica_set(),
    reason="MONGO_URL is not a replica set — transactional rollback test skipped "
           "(run docker-compose.mongo-rs.yml and set MONGO_URL=...?replicaSet=rs0)",
)


def test_write_and_audit_commit_together_on_replica_set():
    """Happy path: with transactions available, the business doc + audit row both
    persist."""
    import core.db
    import core.utils as utils

    async def run():
        client = AsyncIOMotorClient(MONGO_URL)
        dbname = f"gw_txn_{uuid.uuid4().hex[:8]}"
        db = client[dbname]
        core.db.db = db
        utils.db = db
        utils._txn_supported = None  # force re-probe → should detect replica set
        try:
            user = {"id": "u1", "name": "T"}
            doc = await utils.crud_create("widgets", {"name": "W1"}, user=user)
            assert await db.widgets.find_one({"id": doc["id"]}) is not None
            assert await db.audit_logs.find_one({"entity_id": doc["id"]}) is not None
            assert await utils._transactions_available() is True
        finally:
            await client.drop_database(dbname)
            client.close()

    asyncio.run(run())


def test_business_write_rolls_back_when_audit_fails_in_txn(monkeypatch):
    """If the audit insert fails inside the transaction, the business write must
    NOT persist (atomic rollback) — the core guarantee a replica set provides."""
    import core.db
    import core.utils as utils

    async def run():
        client = AsyncIOMotorClient(MONGO_URL)
        dbname = f"gw_txn_{uuid.uuid4().hex[:8]}"
        db = client[dbname]
        core.db.db = db
        utils.db = db
        utils._txn_supported = None
        try:
            user = {"id": "u1", "name": "T"}

            # Force the audit insert to fail *inside* the transaction.
            async def boom(*a, **k):
                raise RuntimeError("simulated audit failure")
            monkeypatch.setattr(utils, "log_audit", boom)

            raised = False
            try:
                await utils.crud_create("widgets", {"name": "W-rollback"}, user=user)
            except Exception:
                raised = True

            assert raised, "the audit failure should propagate"
            # The business write must have rolled back with the transaction.
            leaked = await db.widgets.find_one({"name": "W-rollback"})
            assert leaked is None, "business doc leaked despite audit failure (no rollback!)"
        finally:
            await client.drop_database(dbname)
            client.close()

    asyncio.run(run())
