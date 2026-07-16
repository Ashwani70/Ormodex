"""Migration 017 — Product ↔ Category link.

Backfills ``category_id`` on every product that still has only a legacy
``category`` name. The name is matched (case-insensitively) against the
``product_categories`` master; when no category exists for that name one is
created on the fly, so no product is left unlinked and the Category page shows a
complete catalog.

Idempotent: products that already carry a category_id are skipped, and category
creation is keyed on the normalised name so re-running never duplicates.
"""
import logging
import re

logger = logging.getLogger(__name__)


def _code(name: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name.upper()) if w]
    if len(words) >= 2:
        return "".join(w[0] for w in words)[:6]
    return (words[0][:6] if words else "CAT")


async def run(db):
    from core.utils import new_id, now_iso

    await db.product_categories.create_index("name")

    # Existing categories, keyed by normalised name → id.
    cats = await db.product_categories.find(
        {"is_deleted": {"$ne": True}}, {"_id": 0, "id": 1, "name": 1, "code": 1}
    ).to_list(100000)
    by_name = {(c.get("name") or "").strip().lower(): c["id"] for c in cats}
    used_codes = {c.get("code") for c in cats if c.get("code")}

    async def _ensure_category(name: str) -> str:
        key = name.strip().lower()
        if key in by_name:
            return by_name[key]
        code, base, n = _code(name), _code(name), 1
        while code in used_codes:
            n += 1
            code = f"{base}{n}"
        used_codes.add(code)
        cid = new_id()
        now = now_iso()
        await db.product_categories.insert_one({
            "id": cid, "name": name.strip(), "code": code, "description": None,
            "parent_id": None, "status": "Active", "display_order": len(by_name),
            "is_deleted": False, "created_at": now, "updated_at": now,
        })
        by_name[key] = cid
        return cid

    # Products with a category name but no category_id link yet.
    products = await db.products.find(
        {
            "category": {"$nin": [None, ""]},
            "$or": [{"category_id": None}, {"category_id": {"$exists": False}}],
        },
        {"_id": 0, "id": 1, "category": 1},
    ).to_list(200000)

    linked = 0
    for p in products:
        name = (p.get("category") or "").strip()
        if not name:
            continue
        cid = await _ensure_category(name)
        await db.products.update_one({"id": p["id"]}, {"$set": {"category_id": cid}})
        linked += 1

    logger.info("Migration 017: linked %d products to categories", linked)
