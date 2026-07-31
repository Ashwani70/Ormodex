"""Data & Integration — Module K.

- Tally XML import: dry-run preview → commit (batched). The SAME parse powers
  both, so the preview is trustworthy.
- Generic CSV/Excel import with row-level validation (bad rows reported, good
  rows proceed) + export.
- Scheduled backups (logical dump) + restore-with-confirmation + cold archival
  of closed FYs.
- API keys with scopes + webhook subscriptions (signed, retrying).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from typing import Optional, Literal
from pydantic import BaseModel
import csv
import io
import secrets
import hashlib

from core.auth_utils import get_current_user, require_admin, is_admin_role, bypasses_row_ownership
from core.db import db
from core.utils import now_iso, new_id, next_doc_number, apply_ownership_filter, log_audit
from core.tally_parser import parse_tally_xml, build_preview
from core.webhooks import enqueue_event, deliver_pending

router = APIRouter(prefix="/integration", tags=["Data & Integration"])


def _require_integration(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    if "integration" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "Integration module access required")


# ══════════════════════════════════════════════════════════════
# Tally XML import — dry-run + commit
# ══════════════════════════════════════════════════════════════

@router.post("/import/tally-xml")
async def import_tally_xml(
    file: UploadFile = File(...),
    dryRun: bool = Query(True),
    user: dict = Depends(get_current_user),
):
    """
    Parse a Tally XML export. dryRun=true (default) returns a preview only;
    dryRun=false commits masters + vouchers in batches and returns a post-commit
    reconciliation that ties to the preview counts.
    """
    _require_integration(user)
    raw = await file.read()
    parsed = parse_tally_xml(raw)

    existing = set()
    async for acc in db.chart_of_accounts.find({}, {"_id": 0, "name": 1}):
        existing.add(acc.get("name"))

    preview = build_preview(parsed, existing)

    if dryRun:
        return {"dry_run": True, "preview": preview}

    if not preview["ready_to_commit"]:
        raise HTTPException(400, {"message": "Not ready to commit", "preview": preview})

    # ── Commit masters (ledgers → chart_of_accounts), dedupe by name ──
    committed = {"ledgers": 0, "groups": 0, "stock_items": 0, "vouchers": 0}
    code_seq = await db.chart_of_accounts.count_documents({}) + 9000  # avoid colliding with seeded codes
    batch = []
    for lg in parsed["ledgers"]:
        if lg["name"] in existing:
            continue
        code_seq += 1
        batch.append({
            "id": new_id(), "code": str(code_seq), "name": lg["name"],
            "account_type": lg["account_type"], "opening_balance": lg["opening_balance"],
            "is_active": True, "currency": "INR", "tags": ["tally_import"],
            "source": "tally", "created_at": now_iso(),
        })
        existing.add(lg["name"])
        if len(batch) >= 500:
            await db.chart_of_accounts.insert_many(batch); committed["ledgers"] += len(batch); batch = []
    if batch:
        await db.chart_of_accounts.insert_many(batch); committed["ledgers"] += len(batch)

    # ── Commit vouchers → journal_entries (balanced only) ──
    name_to_code = {}
    async for a in db.chart_of_accounts.find({}, {"_id": 0, "name": 1, "code": 1}):
        name_to_code[a["name"]] = a["code"]

    vbatch = []
    for v in parsed["vouchers"]:
        lines = []
        for ln in v["lines"]:
            code = name_to_code.get(ln["ledger"], "9999")
            lines.append({
                "account_code": code, "account_name": ln["ledger"],
                "debit": ln["amount"] if ln["is_debit"] else 0.0,
                "credit": 0.0 if ln["is_debit"] else ln["amount"],
            })
        vbatch.append({
            "id": new_id(),
            "entry_number": v["number"] or await next_doc_number("TLY", "journal_entries"),
            "date": v["date"], "narration": v["narration"] or f"Tally {v['tally_voucher_type']}",
            "lines": lines, "status": "POSTED", "source": "tally",
            "tally_voucher_type": v["tally_voucher_type"], "created_at": now_iso(),
        })
        if len(vbatch) >= 500:
            await db.journal_entries.insert_many(vbatch); committed["vouchers"] += len(vbatch); vbatch = []
    if vbatch:
        await db.journal_entries.insert_many(vbatch); committed["vouchers"] += len(vbatch)

    # Post-commit reconciliation: committed counts vs preview
    reconciliation = {
        "preview_ledgers_new": preview["ledgers_new"],
        "committed_ledgers": committed["ledgers"],
        "preview_vouchers": preview["summary"]["vouchers"],
        "committed_vouchers": committed["vouchers"],
        "ledgers_reconciled": committed["ledgers"] == preview["ledgers_new"],
        "vouchers_reconciled": committed["vouchers"] == preview["summary"]["vouchers"],
    }
    return {"dry_run": False, "committed": committed, "reconciliation": reconciliation}


# ══════════════════════════════════════════════════════════════
# Generic CSV import with row-level validation
# ══════════════════════════════════════════════════════════════

# Per-entity required columns + a coercion map.
_ENTITY_SCHEMA = {
    "products": {"required": ["name", "sku"], "numeric": ["selling_price", "cost_price", "gst_rate", "quantity"]},
    "customers": {"required": ["name"], "numeric": []},
    "chart_of_accounts": {"required": ["code", "name", "account_type"], "numeric": ["opening_balance"]},
}


class CsvImportRequest(BaseModel):
    entity: str
    rows: list[dict]
    column_map: dict = {}          # csv_col → entity_field
    commit: bool = False


@router.post("/import/csv")
async def import_csv(payload: CsvImportRequest, user: dict = Depends(get_current_user)):
    """
    Validate (and optionally commit) column-mapped rows. Bad rows are reported
    with reasons; good rows still proceed when commit=true.
    """
    _require_integration(user)
    schema = _ENTITY_SCHEMA.get(payload.entity)
    if not schema:
        raise HTTPException(400, f"Unsupported entity '{payload.entity}'. Known: {sorted(_ENTITY_SCHEMA)}")

    good, bad = [], []
    for idx, raw in enumerate(payload.rows):
        # apply column mapping
        row = {payload.column_map.get(k, k): v for k, v in raw.items()}
        errors = []
        for req in schema["required"]:
            if not str(row.get(req, "")).strip():
                errors.append(f"missing required '{req}'")
        for num in schema["numeric"]:
            if row.get(num) not in (None, ""):
                try:
                    row[num] = float(row[num])
                except (ValueError, TypeError):
                    errors.append(f"'{num}' not numeric: {row.get(num)!r}")
        if errors:
            bad.append({"row": idx + 1, "errors": errors, "data": raw})
        else:
            good.append(row)

    committed = 0
    if payload.commit and good:
        docs = []
        for r in good:
            r["id"] = new_id(); r["created_at"] = now_iso(); r["source"] = "csv_import"
            docs.append(r)
        await db[payload.entity].insert_many(docs)
        committed = len(docs)

    return {
        "entity": payload.entity,
        "total_rows": len(payload.rows),
        "valid_rows": len(good),
        "bad_rows": len(bad),
        "errors": bad,
        "committed": committed,
        "committed_flag": payload.commit,
    }


@router.post("/import/csv-file")
async def import_csv_file(entity: str, file: UploadFile = File(...), commit: bool = False,
                          user: dict = Depends(get_current_user)):
    """Parse an uploaded CSV file then run the same validation path."""
    _require_integration(user)
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    rows = list(reader)
    return await import_csv(CsvImportRequest(entity=entity, rows=rows, commit=commit), user)


# ══════════════════════════════════════════════════════════════
# Export
# ══════════════════════════════════════════════════════════════

@router.get("/export/{entity}")
async def export_entity(entity: str, format: Literal["json", "csv"] = "json",
                        user: dict = Depends(get_current_user)):
    _require_integration(user)
    if entity not in _ENTITY_SCHEMA and entity not in ("journal_entries", "invoices", "vouchers"):
        raise HTTPException(400, f"Export not allowed for '{entity}'")
    # Row-ownership: this is a truly generic "export any entity" endpoint, so
    # explicitly apply the same filter every other read path for these
    # collections uses — an unfiltered dump here would otherwise be a silent
    # bypass around every ownership check elsewhere.
    q = apply_ownership_filter({}, user, entity, bypass=bypasses_row_ownership(user.get("role")))
    docs = await db[entity].find(q, {"_id": 0}).to_list(10000)
    await log_audit("EXPORT", entity, "bulk", user, new_values={"format": format, "row_count": len(docs)})
    if format == "json":
        return {"entity": entity, "count": len(docs), "rows": docs}
    # CSV
    if not docs:
        return {"entity": entity, "count": 0, "csv": ""}
    cols = sorted({k for d in docs for k in d.keys() if not isinstance(d[k], (dict, list))})
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for d in docs:
        w.writerow({k: d.get(k) for k in cols})
    return {"entity": entity, "count": len(docs), "csv": out.getvalue()}


# ══════════════════════════════════════════════════════════════
# Backups & archival
# ══════════════════════════════════════════════════════════════

_BACKUP_COLLECTIONS = ["chart_of_accounts", "journal_entries", "invoices", "vouchers",
                       "products", "customers", "vendors", "projects"]


class BackupRequest(BaseModel):
    label: Optional[str] = None
    collections: Optional[list[str]] = None


@router.post("/backups")
async def create_backup(payload: BackupRequest, user: dict = Depends(require_admin)):
    """Logical dump: snapshot selected collections into a backup record."""
    colls = payload.collections or _BACKUP_COLLECTIONS
    snapshot = {}
    counts = {}
    for c in colls:
        docs = await db[c].find({}, {"_id": 0}).to_list(100000)
        snapshot[c] = docs
        counts[c] = len(docs)
    backup = {
        "id": new_id(),
        "label": payload.label or f"backup-{now_iso()[:10]}",
        "collections": colls,
        "counts": counts,
        "total_docs": sum(counts.values()),
        "snapshot": snapshot,
        "created_at": now_iso(),
        "created_by": user["id"],
    }
    await db.backups.insert_one(backup)
    return {"backup_id": backup["id"], "counts": counts, "total_docs": backup["total_docs"]}


@router.get("/backups")
async def list_backups(user: dict = Depends(require_admin)):
    return await db.backups.find({}, {"_id": 0, "snapshot": 0}).sort("created_at", -1).to_list(200)


class RestoreRequest(BaseModel):
    backup_id: str
    confirm: bool = False


@router.post("/backups/restore")
async def restore_backup(payload: RestoreRequest, user: dict = Depends(require_admin)):
    """Restore requires explicit confirmation — it overwrites the listed collections."""
    if not payload.confirm:
        raise HTTPException(400, "Restore must be confirmed (confirm=true) — it overwrites data")
    backup = await db.backups.find_one({"id": payload.backup_id}, {"_id": 0})
    if not backup:
        raise HTTPException(404, "Backup not found")
    restored = {}
    for coll, docs in backup.get("snapshot", {}).items():
        await db[coll].delete_many({})
        if docs:
            await db[coll].insert_many([{**d} for d in docs])
        restored[coll] = len(docs)
    return {"restored": restored, "backup_id": payload.backup_id}


@router.post("/archive-fy")
async def archive_fy(fy: str = Query(...), user: dict = Depends(require_admin)):
    """Cold-archive a closed FY's journal entries into a separate collection."""
    start = f"{fy.split('-')[0]}-04-01"
    end = f"{int(fy.split('-')[0]) + 1}-03-31"
    entries = await db.journal_entries.find(
        {"date": {"$gte": start, "$lte": end}}, {"_id": 0}).to_list(100000)
    if entries:
        await db[f"archive_journal_{fy.replace('-', '_')}"].insert_many([{**e} for e in entries])
    return {"fy": fy, "archived": len(entries), "archive_collection": f"archive_journal_{fy.replace('-', '_')}"}


# ══════════════════════════════════════════════════════════════
# API keys (scoped)
# ══════════════════════════════════════════════════════════════

class ApiKeyRequest(BaseModel):
    name: str
    scopes: list[str] = []


@router.post("/api-keys")
async def create_api_key(payload: ApiKeyRequest, user: dict = Depends(require_admin)):
    """Create a scoped API key. The raw key is shown ONCE; only its hash is stored."""
    raw = "gw_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    doc = {
        "id": new_id(), "name": payload.name, "scopes": payload.scopes,
        "key_hash": key_hash, "key_prefix": raw[:10], "active": True,
        "created_at": now_iso(), "created_by": user["id"],
    }
    await db.api_keys.insert_one(doc)
    return {"id": doc["id"], "name": doc["name"], "scopes": doc["scopes"],
            "api_key": raw, "warning": "Store this key now — it will not be shown again."}


@router.get("/api-keys")
async def list_api_keys(user: dict = Depends(require_admin)):
    return await db.api_keys.find({}, {"_id": 0, "key_hash": 0}).sort("created_at", -1).to_list(200)


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, user: dict = Depends(require_admin)):
    res = await db.api_keys.update_one({"id": key_id}, {"$set": {"active": False, "revoked_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Key not found")
    return {"revoked": key_id}


# ══════════════════════════════════════════════════════════════
# Webhook subscriptions
# ══════════════════════════════════════════════════════════════

WEBHOOK_EVENTS = ["invoice.created", "payment.received", "po.approved",
                  "voucher.posted", "pos.sale", "project.billed"]


class WebhookSubscription(BaseModel):
    url: str
    events: list[str]
    secret: Optional[str] = None
    max_attempts: int = 5


@router.get("/webhooks/events")
async def list_event_types(user: dict = Depends(get_current_user)):
    _require_integration(user)
    return {"events": WEBHOOK_EVENTS}


@router.post("/webhooks/subscriptions")
async def create_subscription(payload: WebhookSubscription, user: dict = Depends(require_admin)):
    bad = [e for e in payload.events if e not in WEBHOOK_EVENTS]
    if bad:
        raise HTTPException(400, f"Unknown events: {bad}. Known: {WEBHOOK_EVENTS}")
    doc = {
        "id": new_id(), "url": payload.url, "events": payload.events,
        "secret": payload.secret or secrets.token_urlsafe(24),
        "max_attempts": payload.max_attempts, "active": True, "created_at": now_iso(),
    }
    await db.webhook_subscriptions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/webhooks/subscriptions")
async def list_subscriptions(user: dict = Depends(require_admin)):
    return await db.webhook_subscriptions.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.delete("/webhooks/subscriptions/{sub_id}")
async def delete_subscription(sub_id: str, user: dict = Depends(require_admin)):
    res = await db.webhook_subscriptions.update_one({"id": sub_id}, {"$set": {"active": False}})
    if res.matched_count == 0:
        raise HTTPException(404, "Subscription not found")
    return {"deactivated": sub_id}


@router.post("/webhooks/test-emit")
async def test_emit(event_type: str, payload: dict, user: dict = Depends(require_admin)):
    """Manually fan an event to subscriptions (for testing integrations)."""
    if event_type not in WEBHOOK_EVENTS:
        raise HTTPException(400, f"Unknown event '{event_type}'")
    n = await enqueue_event(db, event_type, payload)
    return {"event": event_type, "deliveries_queued": n}


@router.post("/webhooks/deliver")
async def trigger_delivery(user: dict = Depends(require_admin)):
    """
    Process due webhook deliveries (signed POST + retry/backoff). Normally a
    scheduled worker calls this; exposed for manual flush. Uses a real HTTP POST.
    """
    import httpx

    async def _post(url, body, headers):
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, content=body,
                                  headers={k: v for k, v in headers.items()} | {"Content-Type": "application/json"})
            return r.status_code

    return await deliver_pending(db, http_post=_post)


@router.get("/webhooks/deliveries")
async def list_deliveries(status: Optional[str] = None, user: dict = Depends(require_admin)):
    filt = {"status": status} if status else {}
    return await db.webhook_deliveries.find(filt, {"_id": 0, "payload": 0}).sort("created_at", -1).to_list(500)
