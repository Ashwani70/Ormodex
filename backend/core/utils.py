import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from .db import db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


async def next_doc_number(prefix: str, collection: str) -> str:
    counter_key = f"{collection}_seq"
    res = await db.counters.find_one_and_update(
        {"_id": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = res["seq"] if res and "seq" in res else 1
    year = datetime.now(timezone.utc).strftime("%y")
    return f"{prefix}-{year}-{seq:05d}"


def calc_totals(items: list) -> dict:
    sub = 0.0
    gst = 0.0
    for it in items:
        line = float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
        sub += line
        gst += line * float(it.get("gst_rate", 0)) / 100.0
    return {
        "subtotal": round(sub, 2),
        "gst_amount": round(gst, 2),
        "total": round(sub + gst, 2),
    }


# ---------- Audit trail (append-only) ----------
# India's audit-trail mandate (Companies Accounts Rules, proviso to Rule 3(1);
# auditor reporting Rule 11(g), effective FY 2023-24) requires every create/edit/
# delete on accounting records to be logged immutably and non-disableably. The
# application NEVER updates or deletes `audit_logs`; for true DB-enforced
# immutability the deployment should grant the app's Mongo role insert+find only
# on this collection (the Mongo equivalent of revoking UPDATE/DELETE grants).
# See AUDIT.md.

# Fields that are noise in a diff (touched on every write) — excluded from changed_fields.
_AUDIT_IGNORED_FIELDS = {"updated_at", "created_at", "_id"}


def _diff_fields(old: dict | None, new: dict | None) -> list[str]:
    """Names of fields whose value actually changed between old and new."""
    old = old or {}
    new = new or {}
    keys = (set(old) | set(new)) - _AUDIT_IGNORED_FIELDS
    return sorted(k for k in keys if old.get(k) != new.get(k))


def build_audit_entry(
    action: str,
    collection_name: str,
    doc_id: str,
    user: dict | None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    ip: str | None = None,
) -> dict:
    """Construct an append-only audit row. `entity_type`/`entity_id` are the
    portable names; `collection_name`/`doc_id` kept as aliases for back-compat."""
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": (user or {}).get("tenant_id"),  # single-tenant today; future-proofed
        "action": action,
        "entity_type": collection_name,
        "entity_id": doc_id,
        "collection_name": collection_name,  # legacy alias
        "doc_id": doc_id,                     # legacy alias
        "user_id": (user or {}).get("id", "system"),
        "user_name": (user or {}).get("name", "System"),
        "before_json": old_values,
        "after_json": new_values,
        "old_values": old_values,             # legacy alias
        "new_values": new_values,             # legacy alias
        "changed_fields": _diff_fields(old_values, new_values) if action == "UPDATE" else None,
        "ip": ip,
        "timestamp": now_iso(),
        "created_at": now_iso(),
    }


async def log_audit(action: str, collection_name: str, doc_id: str, user: dict | None, old_values: dict | None = None, new_values: dict | None = None, ip: str | None = None, session=None):
    if not user:
        return
    entry = build_audit_entry(action, collection_name, doc_id, user, old_values, new_values, ip)
    await db.audit_logs.insert_one(entry, session=session)


# Whether the connected MongoDB supports multi-document transactions (replica set
# or sharded cluster). Cached after first probe. On a standalone server this stays
# False and we fall back to write-then-audit with a compensating rollback.
_txn_supported: bool | None = None


async def _transactions_available() -> bool:
    global _txn_supported
    if _txn_supported is not None:
        return _txn_supported
    try:
        hello = await db.client.admin.command("hello")
        _txn_supported = bool(hello.get("setName") or hello.get("msg") == "isdbgrid")
    except Exception:
        _txn_supported = False
    return _txn_supported


async def _write_with_audit(do_write, action: str, collection: str, doc_id: str,
                            user: dict | None, old_values=None, new_values=None,
                            ip: str | None = None):
    """Run a business write and its audit row as one atomic unit.

    If the server supports transactions, both commit or both roll back. Otherwise
    the write runs first, and if the audit insert fails we compensate by undoing
    the write — so a business change can never persist without its audit row.
    `do_write(session)` performs the write and returns the result.
    """
    if user and await _transactions_available():
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                result = await do_write(session)
                await log_audit(action, collection, doc_id, user,
                                old_values=old_values, new_values=new_values,
                                ip=ip, session=session)
                return result
    # No transactions: write, then audit; compensate the write if audit fails.
    result = await do_write(None)
    if user:
        try:
            await log_audit(action, collection, doc_id, user,
                            old_values=old_values, new_values=new_values, ip=ip)
        except Exception:
            # Roll back the business write so it never persists un-audited.
            if action == "CREATE":
                await db[collection].delete_one({"id": doc_id})
            elif action == "DELETE" and old_values is not None:
                await db[collection].insert_one({k: v for k, v in old_values.items() if k != "_id"})
            elif action == "UPDATE" and old_values is not None:
                await db[collection].replace_one({"id": doc_id}, {k: v for k, v in old_values.items() if k != "_id"})
            raise
    return result


async def crud_create(collection: str, doc: dict, user: dict | None = None, ip: str | None = None) -> dict:
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()

    async def _do(session):
        await db[collection].insert_one(doc, session=session)
        doc.pop("_id", None)  # don't leak Mongo's ObjectId into the audit after_json

    await _write_with_audit(_do, "CREATE", collection, doc["id"], user, new_values=doc, ip=ip)
    doc.pop("_id", None)
    return doc


async def crud_list(collection, q=None, search_fields=None, sort_field="created_at", filt=None):
    f = dict(filt or {})
    if q and search_fields:
        f["$or"] = [{x: {"$regex": q, "$options": "i"}} for x in search_fields]
    return await db[collection].find(f, {"_id": 0}).sort(sort_field, -1).to_list(2000)


async def crud_get(collection: str, item_id: str) -> dict:
    item = await db[collection].find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


async def crud_update(collection: str, item_id: str, update: dict, user: dict | None = None, ip: str | None = None) -> dict:
    old_doc = await db[collection].find_one({"id": item_id}, {"_id": 0})
    if old_doc is None:
        raise HTTPException(status_code=404, detail="Not found")
    update["updated_at"] = now_iso()
    new_doc: dict = {}

    async def _do(session):
        await db[collection].update_one({"id": item_id}, {"$set": update}, session=session)
        fresh = await db[collection].find_one({"id": item_id}, {"_id": 0}, session=session)
        new_doc.update(fresh or {})

    await _write_with_audit(_do, "UPDATE", collection, item_id, user,
                            old_values=old_doc, new_values=new_doc, ip=ip)
    return new_doc


async def crud_delete(collection: str, item_id: str, user: dict | None = None, ip: str | None = None):
    old_doc = await db[collection].find_one({"id": item_id}, {"_id": 0})
    if old_doc is None:
        raise HTTPException(status_code=404, detail="Not found")

    async def _do(session):
        await db[collection].delete_one({"id": item_id}, session=session)

    await _write_with_audit(_do, "DELETE", collection, item_id, user, old_values=old_doc, ip=ip)
    return {"ok": True}
