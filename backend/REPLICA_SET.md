# MongoDB replica set — transactional write+audit

The audit trail's atomicity guarantee (see `AUDIT.md`) uses **multi-document
transactions** so a business write and its audit row commit or roll back together
(`core.utils._write_with_audit`). MongoDB transactions require a **replica set** —
a standalone `mongod` silently can't do them, so the code falls back to a
compensating-write path there.

This doc explains how to run a local single-node replica set so the *true*
transactional path (and `test_txn_rollback_integration.py`) is exercised.

## Start a replica set

```bash
docker compose -f docker-compose.mongo-rs.yml up -d

# one-time: initiate the set (idempotent — safe to re-run)
docker compose -f docker-compose.mongo-rs.yml exec mongo \
  mongosh --quiet --eval 'try{rs.initiate({_id:"rs0",members:[{_id:0,host:"localhost:27017"}]})}catch(e){print(e.message)}'
```

## Point the app / tests at it

```bash
export MONGO_URL="mongodb://localhost:27017/?replicaSet=rs0"
```

With this set, `core.utils._transactions_available()` returns `True` and writes
go through a real transaction.

## Run the transactional-rollback test

```bash
cd backend
MONGO_URL="mongodb://localhost:27017/?replicaSet=rs0" python -m pytest tests/test_txn_rollback_integration.py -v
```

The test **skips** (does not fail) unless `MONGO_URL` points at a replica set, so
it is safe in CI without one. It proves: when the audit insert fails *inside* the
transaction, the business write is rolled back — neither document persists.

## Teardown

```bash
docker compose -f docker-compose.mongo-rs.yml down -v
```

## Note on the gap this closes

Earlier milestones documented that transactional rollback "needs a replica set
(local Mongo is standalone)". This scaffolding is what lets you actually run it;
on standalone deployments the app remains correct via the compensating-write
fallback + the `uniq_voucher_stock_movement` unique index, just not via a server
transaction.
