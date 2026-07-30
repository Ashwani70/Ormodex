"""Fixed Assets router — Module B.

Covers:
- Asset categories (Companies Act useful life / method / residual %)
- IT blocks (Income Tax Act Sec 32 — block of assets, FY-versioned rates)
- Asset register (addition, capitalization)
- Dual depreciation engine:
    * Companies Act Schedule II: SLM or WDV, pro-rated by days held, residual-value floor
    * Income Tax Act Sec 32: block WDV at prescribed rate; half-rate rule (<180 days use)
- Asset transactions: disposal, transfer, revaluation
- Depreciation schedule report (both bases)

Key statutory rules encoded:
- Companies Act residual value defaults to 5% of original cost (configurable per category).
- IT half-rate: if asset put to use < 180 days in the FY of addition, only 50% rate applies.
- IT block disposal: sale consideration reduces block WDV; if block goes negative or is extinguished → STCG.
- Revaluation: creates Revaluation Reserve; adjusts future Companies Act depreciation (new depreciable amount / remaining life).
- Depreciation runs are idempotent per (asset, FY, basis) — re-running a completed run raises 409.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import date

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.utils import now_iso, new_id, next_doc_number, crud_create, crud_list, crud_get, crud_update

router = APIRouter(prefix="/fixed-assets", tags=["Fixed Assets"])


def _require_fa(user: dict):
    if user.get("role") in ("admin", "accountant"):
        return user
    if "fixed_assets" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "Fixed Assets module access required")


# ══════════════════════════════════════════════════════════════
# Pydantic models
# ══════════════════════════════════════════════════════════════

class AssetCategory(BaseModel):
    name: str
    companies_act_useful_life_years: float    # Schedule II useful life
    companies_act_method: Literal["SLM", "WDV"] = "SLM"
    companies_act_residual_pct: float = 5.0   # % of original cost — statutory default 5%
    it_block_id: Optional[str] = None
    description: Optional[str] = None


class ITBlock(BaseModel):
    block_name: str                            # e.g. "Plant & Machinery (15%)"
    asset_type: Literal["tangible", "intangible"] = "tangible"
    it_depreciation_rate: float               # e.g. 15.0 for 15%
    financial_year: str                        # "2024-25"
    effective_from: str                        # ISO date
    effective_to: Optional[str] = None


class FixedAsset(BaseModel):
    code: Optional[str] = None
    description: str
    category_id: str
    purchase_date: str                        # ISO date
    capitalized_date: str                     # date put to use
    gross_value: float                        # original cost INR
    salvage_value: float = 0.0               # Companies Act residual (0 → use category %)
    qty: float = 1.0
    branch_id: Optional[str] = None
    location: Optional[str] = None
    supplier_id: Optional[str] = None
    invoice_ref: Optional[str] = None
    status: Literal["ACTIVE", "DISPOSED", "TRANSFERRED", "WRITTEN_OFF"] = "ACTIVE"
    notes: Optional[str] = None


class DepreciationRunRequest(BaseModel):
    financial_year: str                       # e.g. "2024-25"
    basis: Literal["companies_act", "income_tax"]
    asset_ids: Optional[list] = None          # None → run for all active assets
    preview: bool = False                     # if True, compute but do not persist


class DisposalRequest(BaseModel):
    disposal_date: str
    sale_consideration: float
    financial_year: str
    notes: Optional[str] = None


class TransferRequest(BaseModel):
    transfer_date: str
    to_branch_id: str
    to_location: Optional[str] = None
    notes: Optional[str] = None


class RevaluationRequest(BaseModel):
    revaluation_date: str
    new_gross_value: float
    financial_year: str
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# Depreciation computation helpers
# ══════════════════════════════════════════════════════════════

def _fy_bounds(fy: str) -> tuple[date, date]:
    """Return (start, end) for a financial year string like '2024-25'."""
    parts = fy.split("-")
    start_yr = int(parts[0])
    return date(start_yr, 4, 1), date(start_yr + 1, 3, 31)


def _days_in_fy(fy: str) -> int:
    s, e = _fy_bounds(fy)
    return (e - s).days + 1


def _days_held_in_fy(capitalized_date_str: str, fy: str, disposal_date_str: Optional[str] = None) -> int:
    """Days the asset was in use within the given FY (for Companies Act pro-ration)."""
    cap = date.fromisoformat(capitalized_date_str)
    fy_start, fy_end = _fy_bounds(fy)
    effective_start = max(cap, fy_start)
    effective_end = date.fromisoformat(disposal_date_str) if disposal_date_str else fy_end
    effective_end = min(effective_end, fy_end)
    if effective_start > effective_end:
        return 0
    return (effective_end - effective_start).days + 1


def _companies_act_slm(gross: float, residual: float, life_years: float, days_held: int, total_days: int) -> float:
    """
    SLM depreciation for Companies Act.
    Annual charge = (Gross - Residual) / UsefulLife
    Pro-rated by days held / days in FY.
    """
    depreciable = max(gross - residual, 0.0)
    annual = depreciable / life_years if life_years > 0 else 0.0
    return round(annual * days_held / total_days, 2)


def _companies_act_wdv(opening_wdv: float, residual: float, life_years: float,
                        gross: float, days_held: int, total_days: int) -> float:
    """
    WDV depreciation for Companies Act.
    WDV rate = 1 - (Residual/Gross)^(1/n)
    Pro-rated by days held.
    """
    if life_years <= 0 or gross <= 0:
        return 0.0
    residual_ratio = max(residual, 0.0) / gross
    rate = 1.0 - (residual_ratio ** (1.0 / life_years))
    annual = opening_wdv * rate
    charged = annual * days_held / total_days
    # Do not depreciate below residual value
    return round(min(charged, opening_wdv - residual), 2)


def _it_depreciation(block_wdv: float, it_rate: float, additions: float,
                      disposals: float, half_rate_additions: float) -> dict:
    """
    Income Tax Act block depreciation.

    block_wdv      : Opening WDV of the block at start of FY
    it_rate        : Prescribed rate (e.g. 15.0 for 15%)
    additions      : Cost of assets added to block AND put to use ≥ 180 days
    disposals      : Sale consideration of assets disposed in FY
    half_rate_additions: Cost of assets added AND put to use < 180 days

    Returns dict with depreciation and closing WDV.
    STCG arises if (block_wdv + additions - disposals) < 0 after deducting depreciation.
    """
    rate = it_rate / 100.0

    # Block base after additions and disposals
    block_after = block_wdv + additions + half_rate_additions - disposals

    if block_after <= 0:
        # Block extinguished or negative → STCG
        stcg = abs(block_after)
        return {
            "opening_wdv": block_wdv,
            "additions": additions,
            "half_rate_additions": half_rate_additions,
            "disposals": disposals,
            "depreciation": 0.0,
            "closing_wdv": 0.0,
            "stcg": round(stcg, 2),
            "block_extinguished": True,
        }

    # Full-rate depreciation on (block_wdv + full additions - disposals)
    full_rate_base = block_wdv + additions - disposals
    depr_full = max(full_rate_base, 0.0) * rate

    # Half-rate on additions used < 180 days
    depr_half = half_rate_additions * rate * 0.5

    total_depr = round(depr_full + depr_half, 2)
    closing_wdv = round(block_after - total_depr, 2)

    return {
        "opening_wdv": block_wdv,
        "additions": additions,
        "half_rate_additions": half_rate_additions,
        "disposals": disposals,
        "depreciation": total_depr,
        "closing_wdv": max(closing_wdv, 0.0),
        "stcg": 0.0,
        "block_extinguished": False,
    }


def _put_to_use_days(capitalized_date_str: str, fy: str) -> int:
    """Days from capitalization to FY end — used for IT half-rate test."""
    cap = date.fromisoformat(capitalized_date_str)
    _, fy_end = _fy_bounds(fy)
    return max(0, (fy_end - cap).days + 1)


# ══════════════════════════════════════════════════════════════
# Asset Category Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/categories")
async def list_categories(user: dict = Depends(get_current_user)):
    _require_fa(user)
    return await crud_list("asset_categories", sort_field="name")


@router.post("/categories")
async def create_category(payload: AssetCategory, user: dict = Depends(require_admin)):
    return await crud_create("asset_categories", payload.model_dump(), user)


@router.put("/categories/{cat_id}")
async def update_category(cat_id: str, payload: AssetCategory, user: dict = Depends(require_admin)):
    return await crud_update("asset_categories", cat_id, payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# IT Block Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/it-blocks")
async def list_it_blocks(fy: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_fa(user)
    filt = {}
    if fy:
        filt["financial_year"] = fy
    return await crud_list("it_blocks", filt=filt, sort_field="block_name")


@router.post("/it-blocks")
async def create_it_block(payload: ITBlock, user: dict = Depends(require_admin)):
    return await crud_create("it_blocks", payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Asset Register Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/assets")
async def list_assets(
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_fa(user)
    filt: dict = {}
    if category_id:
        filt["category_id"] = category_id
    if branch_id:
        filt["branch_id"] = branch_id
    if status:
        filt["status"] = status
    
    return await crud_list("fixed_assets", q, ["description", "code", "location"], filt=filt)


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str, user: dict = Depends(get_current_user)):
    _require_fa(user)
    asset = await crud_get("fixed_assets", asset_id)
    # Enrich with latest depreciation runs
    ca_run = await db.asset_depreciation_runs.find_one(
        {"asset_id": asset_id, "basis": "companies_act"},
        {"_id": 0},
        sort=[("financial_year", -1)],
    )
    it_run = await db.asset_depreciation_runs.find_one(
        {"asset_id": asset_id, "basis": "income_tax"},
        {"_id": 0},
        sort=[("financial_year", -1)],
    )
    asset["latest_ca_run"] = ca_run
    asset["latest_it_run"] = it_run
    return asset


@router.post("/assets")
async def create_asset(payload: FixedAsset, user: dict = Depends(get_current_user)):
    _require_fa(user)

    # Validate category exists
    cat = await db.asset_categories.find_one({"id": payload.category_id})
    if not cat:
        raise HTTPException(400, f"Asset category '{payload.category_id}' not found")

    doc = payload.model_dump()
    doc["code"] = doc.get("code") or await next_doc_number("FA", "fixed_assets")

    # Default salvage to category residual %
    if not doc.get("salvage_value"):
        doc["salvage_value"] = round(payload.gross_value * cat["companies_act_residual_pct"] / 100.0, 2)

    doc["ca_opening_wdv"] = payload.gross_value   # Companies Act WDV
    doc["it_cost_for_block"] = payload.gross_value  # cost to add to IT block on first run

    return await crud_create("fixed_assets", doc, user)


# ══════════════════════════════════════════════════════════════
# Depreciation Run Endpoint
# ══════════════════════════════════════════════════════════════

@router.post("/depreciation/run")
async def run_depreciation(
    payload: DepreciationRunRequest,
    user: dict = Depends(get_current_user),
):
    """
    Compute and (optionally) persist depreciation for a financial year.

    Companies Act basis:
      - Per-asset SLM or WDV, pro-rated by days held, floor at residual value.

    Income Tax basis:
      - Per IT block: block WDV * rate; half-rate for <180-day additions; STCG if block negative.

    Set preview=True to get results without persisting.
    """
    _require_fa(user)

    fy = payload.financial_year
    fy_start, fy_end = _fy_bounds(fy)
    total_fy_days = _days_in_fy(fy)

    # Load assets to process
    asset_filter: dict = {"status": "ACTIVE"}
    if payload.asset_ids:
        asset_filter["id"] = {"$in": payload.asset_ids}
    assets = await db.fixed_assets.find(asset_filter, {"_id": 0}).to_list(5000)

    results = []
    # Collected across the per-asset/per-block loops below and written in ONE
    # chunked insert_many + ONE bulk_update_by_id at the end of each section,
    # instead of an insert_one + update_one pair per asset/block inside the
    # loop — was up to 2x(assets processed) individual round trips on a full
    # depreciation run. The per-asset READS inside these loops (category,
    # prior-run lookups) are unrelated to this batching pass and unchanged.
    new_run_docs: list = []
    asset_updates_by_id: dict = {}

    # ── Companies Act ─────────────────────────────────────────────────────────
    if payload.basis == "companies_act":
        for asset in assets:
            cat = await db.asset_categories.find_one({"id": asset["category_id"]})
            if not cat:
                continue

            # Idempotency check
            existing = await db.asset_depreciation_runs.find_one(
                {"asset_id": asset["id"], "financial_year": fy, "basis": "companies_act"}
            )
            if existing and not payload.preview:
                raise HTTPException(409, f"Companies Act depreciation already run for asset {asset['code']} FY {fy}")

            cap_date = asset.get("capitalized_date") or asset.get("purchase_date", str(fy_start))
            days_held = _days_held_in_fy(cap_date, fy)
            if days_held == 0:
                continue  # not in use this FY

            gross = float(asset.get("gross_value", 0))
            residual = float(asset.get("salvage_value", 0))
            life_yrs = float(cat.get("companies_act_useful_life_years", 10))
            method = cat.get("companies_act_method", "SLM")

            # Opening WDV: check last run; else gross value
            prior_run = await db.asset_depreciation_runs.find_one(
                {"asset_id": asset["id"], "basis": "companies_act"},
                sort=[("financial_year", -1)],
            )
            opening_wdv = float(prior_run["closing_wdv"]) if prior_run else gross

            if opening_wdv <= residual:
                # Fully depreciated
                depr = 0.0
                closing_wdv = residual
            elif method == "SLM":
                depr = _companies_act_slm(gross, residual, life_yrs, days_held, total_fy_days)
                closing_wdv = max(round(opening_wdv - depr, 2), residual)
                depr = round(opening_wdv - closing_wdv, 2)  # actual charged (may be floored)
            else:  # WDV
                depr = _companies_act_wdv(opening_wdv, residual, life_yrs, gross, days_held, total_fy_days)
                closing_wdv = max(round(opening_wdv - depr, 2), residual)
                depr = round(opening_wdv - closing_wdv, 2)

            run_doc = {
                "asset_id": asset["id"],
                "asset_code": asset.get("code", ""),
                "asset_description": asset.get("description", ""),
                "financial_year": fy,
                "basis": "companies_act",
                "method": method,
                "opening_wdv": opening_wdv,
                "gross_value": gross,
                "residual_value": residual,
                "days_held": days_held,
                "total_fy_days": total_fy_days,
                "depreciation": depr,
                "closing_wdv": closing_wdv,
                "is_fully_depreciated": closing_wdv <= residual,
            }
            results.append(run_doc)

            if not payload.preview:
                run_doc["id"] = new_id()
                run_doc["created_at"] = now_iso()
                new_run_docs.append(run_doc)
                # Update asset's Companies Act WDV
                asset_updates_by_id[asset["id"]] = {"$set": {"ca_opening_wdv": closing_wdv, "updated_at": now_iso()}}

    # ── Income Tax Act ────────────────────────────────────────────────────────
    else:  # income_tax
        # Group assets by IT block
        blocks: dict = {}   # block_id → {block_doc, assets: []}
        for asset in assets:
            cat = await db.asset_categories.find_one({"id": asset["category_id"]})
            if not cat or not cat.get("it_block_id"):
                continue
            bid = cat["it_block_id"]
            if bid not in blocks:
                block = await db.it_blocks.find_one({"id": bid}, {"_id": 0})
                if not block:
                    continue
                blocks[bid] = {"block": block, "assets": []}
            blocks[bid]["assets"].append(asset)

        for bid, entry in blocks.items():
            block = entry["block"]
            block_assets = entry["assets"]

            # Idempotency per block
            existing = await db.asset_depreciation_runs.find_one(
                {"block_id": bid, "financial_year": fy, "basis": "income_tax"}
            )
            if existing and not payload.preview:
                raise HTTPException(409, f"IT depreciation already run for block '{block['block_name']}' FY {fy}")

            it_rate = float(block.get("it_depreciation_rate", 15.0))

            # Block opening WDV = sum of prior closing WDVs (or original cost for new assets)
            prior_block_run = await db.asset_depreciation_runs.find_one(
                {"block_id": bid, "basis": "income_tax"},
                sort=[("financial_year", -1)],
            )
            block_opening_wdv = float(prior_block_run["closing_wdv"]) if prior_block_run else 0.0

            additions = 0.0         # put to use ≥ 180 days in FY
            half_rate_additions = 0.0  # put to use < 180 days in FY
            disposals = 0.0         # total sale consideration of disposed assets this FY

            for asset in block_assets:
                cap_date = asset.get("capitalized_date") or asset.get("purchase_date", str(fy_start))
                try:
                    cap = date.fromisoformat(cap_date)
                except ValueError:
                    cap = fy_start

                # Is this a new addition in this FY?
                if fy_start <= cap <= fy_end:
                    days_used = _put_to_use_days(cap_date, fy)
                    cost = float(asset.get("it_cost_for_block") or asset.get("gross_value", 0))
                    if days_used >= 180:
                        additions += cost
                    else:
                        half_rate_additions += cost
                elif cap < fy_start:
                    # Already in block — its WDV is captured in block_opening_wdv from prior run
                    pass

                # Disposals in this FY
                disposal_txns = await db.asset_transactions.find(
                    {"asset_id": asset["id"], "type": "disposal",
                     "date": {"$gte": str(fy_start), "$lte": str(fy_end)}},
                    {"_id": 0},
                ).to_list(100)
                for txn in disposal_txns:
                    disposals += float(txn.get("amount", 0))

            calc = _it_depreciation(block_opening_wdv, it_rate, additions, disposals, half_rate_additions)
            calc["block_id"] = bid
            calc["block_name"] = block.get("block_name", "")
            calc["financial_year"] = fy
            calc["basis"] = "income_tax"
            calc["it_rate"] = it_rate
            results.append(calc)

            if not payload.preview:
                run_doc = {**calc, "id": new_id(), "created_at": now_iso()}
                new_run_docs.append(run_doc)
                # Update each asset's IT WDV proportionally
                total_block_cost = additions + half_rate_additions + block_opening_wdv
                if total_block_cost > 0:
                    ratio = calc["closing_wdv"] / total_block_cost
                    for asset in block_assets:
                        asset_cost = float(asset.get("it_cost_for_block") or asset.get("gross_value", 0))
                        asset_updates_by_id[asset["id"]] = {
                            "$set": {"it_opening_wdv": round(asset_cost * ratio, 2), "updated_at": now_iso()}
                        }

    if new_run_docs:
        for i in range(0, len(new_run_docs), 500):
            await db.asset_depreciation_runs.insert_many(new_run_docs[i:i + 500])
    if asset_updates_by_id:
        await db.fixed_assets.bulk_update_by_id(asset_updates_by_id)

    return {
        "financial_year": fy,
        "basis": payload.basis,
        "preview": payload.preview,
        "assets_processed": len(results),
        "results": results,
        "total_depreciation": round(sum(r.get("depreciation", 0) for r in results), 2),
    }


# ══════════════════════════════════════════════════════════════
# Disposal
# ══════════════════════════════════════════════════════════════

@router.post("/assets/{asset_id}/dispose")
async def dispose_asset(
    asset_id: str,
    payload: DisposalRequest,
    user: dict = Depends(get_current_user),
):
    """
    Dispose of an asset.

    Companies Act: gain/loss = Sale consideration - Companies Act closing WDV.
    IT Act: sale consideration reduces the IT block WDV; if block goes negative → STCG.
    Asset status set to DISPOSED (soft delete; original record preserved).
    """
    _require_fa(user)
    asset = await crud_get("fixed_assets", asset_id)
    if asset["status"] == "DISPOSED":
        raise HTTPException(400, "Asset is already disposed")

    gross = float(asset.get("gross_value", 0))
    ca_wdv = float(asset.get("ca_opening_wdv") or gross)
    sale = payload.sale_consideration

    # Companies Act gain/loss
    ca_gain_loss = round(sale - ca_wdv, 2)
    ca_gain_loss_type = "GAIN" if ca_gain_loss > 0 else ("LOSS" if ca_gain_loss < 0 else "NIL")

    # IT block impact (mark the block WDV reduction — actual block recomputed on next IT run)
    it_impact = {
        "sale_consideration": sale,
        "note": "Reduce IT block WDV by sale consideration on next IT depreciation run",
    }

    txn = {
        "asset_id": asset_id,
        "asset_code": asset.get("code", ""),
        "type": "disposal",
        "date": payload.disposal_date,
        "financial_year": payload.financial_year,
        "amount": sale,
        "ca_wdv_at_disposal": ca_wdv,
        "ca_gain_loss": ca_gain_loss,
        "ca_gain_loss_type": ca_gain_loss_type,
        "it_impact": it_impact,
        "notes": payload.notes,
    }
    txn_doc = await crud_create("asset_transactions", txn, user)

    # Mark asset disposed
    await crud_update(
        "fixed_assets", asset_id,
        {"status": "DISPOSED", "disposal_date": payload.disposal_date,
         "disposal_sale_value": sale, "ca_gain_loss": ca_gain_loss},
        user,
    )

    return {
        "asset_id": asset_id,
        "transaction": txn_doc,
        "companies_act": {
            "wdv_at_disposal": ca_wdv,
            "sale_consideration": sale,
            "gain_loss": ca_gain_loss,
            "gain_loss_type": ca_gain_loss_type,
        },
        "income_tax": it_impact,
    }


# ══════════════════════════════════════════════════════════════
# Transfer
# ══════════════════════════════════════════════════════════════

@router.post("/assets/{asset_id}/transfer")
async def transfer_asset(
    asset_id: str,
    payload: TransferRequest,
    user: dict = Depends(get_current_user),
):
    _require_fa(user)
    asset = await crud_get("fixed_assets", asset_id)
    if asset["status"] != "ACTIVE":
        raise HTTPException(400, f"Cannot transfer asset in status '{asset['status']}'")

    txn = {
        "asset_id": asset_id,
        "asset_code": asset.get("code", ""),
        "type": "transfer",
        "date": payload.transfer_date,
        "amount": 0.0,
        "from_branch_id": asset.get("branch_id"),
        "to_branch_id": payload.to_branch_id,
        "to_location": payload.to_location,
        "notes": payload.notes,
    }
    txn_doc = await crud_create("asset_transactions", txn, user)

    await crud_update(
        "fixed_assets", asset_id,
        {"branch_id": payload.to_branch_id, "location": payload.to_location,
         "status": "TRANSFERRED"},
        user,
    )
    return txn_doc


# ══════════════════════════════════════════════════════════════
# Revaluation
# ══════════════════════════════════════════════════════════════

@router.post("/assets/{asset_id}/revalue")
async def revalue_asset(
    asset_id: str,
    payload: RevaluationRequest,
    user: dict = Depends(get_current_user),
):
    """
    Revalue an asset (upward or downward).

    Upward revaluation:
      - Difference credited to Revaluation Reserve.
      - Future Companies Act depreciation = new depreciable amount / remaining useful life.

    Downward revaluation:
      - First reduces Revaluation Reserve; excess charged to P&L.
    """
    _require_fa(user)
    asset = await crud_get("fixed_assets", asset_id)
    if asset["status"] != "ACTIVE":
        raise HTTPException(400, f"Cannot revalue asset in status '{asset['status']}'")

    cat = await db.asset_categories.find_one({"id": asset["category_id"]})
    if not cat:
        raise HTTPException(400, "Asset category not found")

    old_gross = float(asset.get("gross_value", 0))
    new_gross = payload.new_gross_value
    ca_wdv = float(asset.get("ca_opening_wdv") or old_gross)
    revaluation_surplus = round(new_gross - old_gross, 2)

    # Estimate remaining life
    cap_date = date.fromisoformat(asset.get("capitalized_date") or asset.get("purchase_date", "2020-01-01"))
    today = date.today()
    years_used = max(0.0, (today - cap_date).days / 365.25)
    life_yrs = float(cat.get("companies_act_useful_life_years", 10))
    remaining_life = max(1.0, life_yrs - years_used)

    # New annual SLM charge after revaluation
    new_residual = new_gross * cat.get("companies_act_residual_pct", 5.0) / 100.0
    new_depreciable = max(new_gross - new_residual, 0.0)
    new_annual_depr = round(new_depreciable / remaining_life, 2)

    txn = {
        "asset_id": asset_id,
        "asset_code": asset.get("code", ""),
        "type": "revaluation",
        "date": payload.revaluation_date,
        "financial_year": payload.financial_year,
        "amount": new_gross,
        "old_gross_value": old_gross,
        "new_gross_value": new_gross,
        "revaluation_surplus": revaluation_surplus,
        "revaluation_type": "UPWARD" if revaluation_surplus >= 0 else "DOWNWARD",
        "new_annual_ca_depreciation": new_annual_depr,
        "remaining_life_years": round(remaining_life, 2),
        "notes": payload.notes,
    }
    txn_doc = await crud_create("asset_transactions", txn, user)

    await crud_update(
        "fixed_assets", asset_id,
        {
            "gross_value": new_gross,
            "ca_opening_wdv": round(ca_wdv + revaluation_surplus, 2),
            "salvage_value": round(new_residual, 2),
            "revaluation_surplus_reserve": round(
                float(asset.get("revaluation_surplus_reserve", 0)) + max(revaluation_surplus, 0), 2
            ),
        },
        user,
    )

    return {
        "asset_id": asset_id,
        "transaction": txn_doc,
        "revaluation_surplus": revaluation_surplus,
        "new_annual_ca_depreciation": new_annual_depr,
        "remaining_life_years": round(remaining_life, 2),
        "accounting_treatment": (
            f"Credit Revaluation Reserve ₹{max(revaluation_surplus,0):,.2f}"
            if revaluation_surplus >= 0
            else f"Debit P&L (impairment) ₹{abs(revaluation_surplus):,.2f}"
        ),
    }


# ══════════════════════════════════════════════════════════════
# Depreciation Schedule Report
# ══════════════════════════════════════════════════════════════

@router.get("/depreciation-schedule")
async def depreciation_schedule(
    basis: Literal["companies_act", "income_tax"] = Query("companies_act"),
    financial_year: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """
    Full depreciation schedule — both bases side by side for an FY.
    Supports drill-down: each row links to the source asset.
    """
    _require_fa(user)

    filt: dict = {"basis": basis}
    if financial_year:
        filt["financial_year"] = financial_year

    runs = await db.asset_depreciation_runs.find(filt, {"_id": 0}).sort("financial_year", 1).to_list(5000)

    # Batch-read every referenced asset + category in TWO queries instead of
    # a find_one-per-row loop (was an N+1 — up to 1 + 2×5000 round trips).
    asset_ids = list({r.get("asset_id") for r in runs if r.get("asset_id")})
    assets_by_id: dict = {}
    if asset_ids:
        assets = await db.fixed_assets.find({"id": {"$in": asset_ids}}, {"_id": 0}).to_list(len(asset_ids))
        assets_by_id = {a["id"]: a for a in assets}

    category_ids = list({a.get("category_id") for a in assets_by_id.values() if a.get("category_id")})
    categories_by_id: dict = {}
    if category_ids:
        cats = await db.asset_categories.find({"id": {"$in": category_ids}}, {"_id": 0}).to_list(len(category_ids))
        categories_by_id = {c["id"]: c for c in cats}

    # Enrich with asset details and optionally filter by category
    enriched = []
    for run in runs:
        asset = assets_by_id.get(run.get("asset_id"))
        if not asset:
            enriched.append(run)
            continue
        if category_id and asset.get("category_id") != category_id:
            continue
        cat = categories_by_id.get(asset.get("category_id"))
        enriched.append({
            **run,
            "asset_code": asset.get("code", ""),
            "asset_description": asset.get("description", ""),
            "category_name": cat.get("name", "") if cat else "",
            "branch_id": asset.get("branch_id"),
        })

    return {
        "basis": basis,
        "financial_year": financial_year,
        "total_depreciation": round(sum(r.get("depreciation", 0) for r in enriched), 2),
        "rows": enriched,
    }


# ══════════════════════════════════════════════════════════════
# Asset Transactions Log
# ══════════════════════════════════════════════════════════════

@router.get("/assets/{asset_id}/transactions")
async def list_asset_transactions(asset_id: str, user: dict = Depends(get_current_user)):
    _require_fa(user)
    txns = await db.asset_transactions.find({"asset_id": asset_id}, {"_id": 0}).sort("date", 1).to_list(500)
    return txns


@router.get("/transactions")
async def list_all_transactions(
    txn_type: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_fa(user)
    filt = {}
    if txn_type:
        filt["type"] = txn_type
    return await db.asset_transactions.find(filt, {"_id": 0}).sort("date", -1).to_list(1000)
