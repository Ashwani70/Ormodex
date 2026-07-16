"""Masters subsystem — accounting + inventory master CRUD.

All endpoints are tenant-scoped (core.tenant), audited and soft-delete only
(core.masters_crud). RBAC: admin or the `masters`/`accounting`/`inventory`
module permission. Masters are not side-effecting, so they bypass maker-checker
(only ledger/inventory-posting vouchers go through it).

Mounted at /masters.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.auth_utils import get_current_user, is_admin_role
from core.db import db
from core.masters_crud import (
    masters_create, masters_list, masters_list_paginated, masters_soft_delete,
    masters_update, singleton_get, singleton_upsert,
)
from core.masters_models import (
    CompanyGstDetails, Currency, CurrencyUpdate, Group, GroupUpdate,
    GstClassification, GstClassificationUpdate, GstRegistration, GstRegistrationUpdate,
    Ledger, LedgerUpdate, Location, LocationUpdate, PanCinDetails,
    RateOfExchange, RateOfExchangeUpdate, StockCategory, StockCategoryUpdate,
    StockGroup, StockGroupUpdate, StockItem, StockItemUpdate, TcsDetails,
    TcsNatureOfGoods, TcsNatureOfGoodsUpdate, TdsDetails, TdsNatureOfPayment,
    TdsNatureOfPaymentUpdate, Unit, UnitUpdate, VoucherType, VoucherTypeUpdate,
)
from core.tenant import tenant_ctx, tenant_filter

router = APIRouter(prefix="/masters", tags=["Masters"])

# Collections (compound (tenant_id, ...) indexes created in server startup).
COLL = {
    "groups": "master_groups",
    "ledgers": "master_ledgers",
    "currencies": "master_currencies",
    "rates": "master_rates_of_exchange",
    "voucher-types": "master_voucher_types",
    "stock-groups": "master_stock_groups",
    "stock-categories": "master_stock_categories",
    "stock-items": "master_stock_items",
    "units": "master_units",
    "locations": "master_locations",
    # Statutory list masters
    "gst-registrations": "master_gst_registrations",
    "gst-classifications": "master_gst_classifications",
    "tds-nature-of-payment": "master_tds_nature_of_payment",
    "tcs-nature-of-goods": "master_tcs_nature_of_goods",
}

# Statutory singletons — one document per tenant (get + upsert only).
SINGLETON_COLL = {
    "company-gst-details": "statutory_company_gst_details",
    "tds-details": "statutory_tds_details",
    "tcs-details": "statutory_tcs_details",
    "pan-cin-details": "statutory_pan_cin_details",
}


def _require_masters(user: dict) -> dict:
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    perms = user.get("module_permissions") or []
    if any(p in perms for p in ("masters", "accounting", "inventory")):
        return user
    raise HTTPException(403, "Masters module access required")


def _clean(update_model) -> dict:
    """Strip unset/None fields from an *Update model so PATCH is partial."""
    return {k: v for k, v in update_model.model_dump(exclude_unset=True).items()}


async def _list_response(collection, tenant, *, q=None, search_fields=None, extra=None,
                         sort_field="name", page=None, limit=None,
                         from_date=None, to_date=None):
    """Shared list responder. When pagination params are supplied returns the
    paginated envelope {items,total,page,limit,pages}; otherwise the plain array
    (back-compat with the existing MasterScreen, which reads a bare list)."""
    if page is not None or limit is not None or from_date or to_date:
        return await masters_list_paginated(
            collection, tenant, q=q, search_fields=search_fields, extra=extra,
            sort_field=sort_field, page=page or 1, limit=limit or 50,
            from_date=from_date, to_date=to_date)
    return await masters_list(collection, tenant, q=q, search_fields=search_fields,
                              extra=extra, sort_field=sort_field)


# ════════════════════════ Accounting: Group (tree) ════════════════════════

@router.get("/groups")
async def list_groups(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                      from_date: Optional[str] = None, to_date: Optional[str] = None,
                      tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await _list_response(COLL["groups"], tenant, q=q, search_fields=["name", "nature"],
                                page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/groups")
async def create_group(payload: Group, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["groups"], payload.model_dump(), tenant, user,
                                unique_fields=["name"], parent_field="parent_group_id")


@router.put("/groups/{item_id}")
async def update_group(item_id: str, payload: GroupUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["groups"], item_id, _clean(payload), tenant, user,
                                unique_fields=["name"], parent_field="parent_group_id")


@router.delete("/groups/{item_id}")
async def delete_group(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["groups"], item_id, tenant, user, child_parent_field="parent_group_id")


# ════════════════════════ Accounting: Ledger ════════════════════════

@router.get("/ledgers")
async def list_ledgers(q: Optional[str] = None, group_id: Optional[str] = None,
                       page: Optional[int] = None, limit: Optional[int] = None,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    extra = {"group_id": group_id} if group_id else None
    return await _list_response(COLL["ledgers"], tenant, q=q, search_fields=["name", "gstin", "pan"],
                                extra=extra, page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/ledgers")
async def create_ledger(payload: Ledger, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = payload.model_dump()
    await _ensure_ref(COLL["groups"], data["group_id"], tenant, "group_id")
    await _ensure_coa_account(data["coa_account_id"])
    return await masters_create(COLL["ledgers"], data, tenant, user, unique_fields=["name"])


@router.put("/ledgers/{item_id}")
async def update_ledger(item_id: str, payload: LedgerUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = _clean(payload)
    if "group_id" in data:
        await _ensure_ref(COLL["groups"], data["group_id"], tenant, "group_id")
    if "coa_account_id" in data:
        await _ensure_coa_account(data["coa_account_id"])
    return await masters_update(COLL["ledgers"], item_id, data, tenant, user, unique_fields=["name"])


@router.delete("/ledgers/{item_id}")
async def delete_ledger(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["ledgers"], item_id, tenant, user)


# ════════════════════════ Accounting: Currency ════════════════════════

@router.get("/currencies")
async def list_currencies(q: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_list(COLL["currencies"], tenant, q=q, search_fields=["iso_code", "formal_name", "symbol"], sort_field="iso_code")


@router.post("/currencies")
async def create_currency(payload: Currency, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = payload.model_dump()
    if data.get("is_base_currency"):
        await _ensure_single_base_currency(tenant, exclude_id=None)
    return await masters_create(COLL["currencies"], data, tenant, user, unique_fields=["iso_code"])


@router.put("/currencies/{item_id}")
async def update_currency(item_id: str, payload: CurrencyUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = _clean(payload)
    if data.get("is_base_currency"):
        await _ensure_single_base_currency(tenant, exclude_id=item_id)
    return await masters_update(COLL["currencies"], item_id, data, tenant, user, unique_fields=["iso_code"])


@router.delete("/currencies/{item_id}")
async def delete_currency(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["currencies"], item_id, tenant, user)


# ════════════════════════ Accounting: Rate of Exchange ════════════════════════

@router.get("/rates")
async def list_rates(currency_id: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    extra = {"currency_id": currency_id} if currency_id else None
    return await masters_list(COLL["rates"], tenant, extra=extra, sort_field="effective_date")


@router.post("/rates")
async def create_rate(payload: RateOfExchange, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = payload.model_dump()
    await _ensure_ref(COLL["currencies"], data["currency_id"], tenant, "currency_id")
    return await masters_create(COLL["rates"], data, tenant, user)


@router.put("/rates/{item_id}")
async def update_rate(item_id: str, payload: RateOfExchangeUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["rates"], item_id, _clean(payload), tenant, user)


@router.delete("/rates/{item_id}")
async def delete_rate(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["rates"], item_id, tenant, user)


# ════════════════════════ Accounting: Voucher Type ════════════════════════

@router.get("/voucher-types")
async def list_voucher_types(q: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_list(COLL["voucher-types"], tenant, q=q, search_fields=["name", "parent_type"])


@router.post("/voucher-types")
async def create_voucher_type(payload: VoucherType, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["voucher-types"], payload.model_dump(), tenant, user, unique_fields=["name"])


@router.put("/voucher-types/{item_id}")
async def update_voucher_type(item_id: str, payload: VoucherTypeUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["voucher-types"], item_id, _clean(payload), tenant, user, unique_fields=["name"])


@router.delete("/voucher-types/{item_id}")
async def delete_voucher_type(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["voucher-types"], item_id, tenant, user)


# ════════════════════════ Inventory: Stock Group (tree) ════════════════════════

@router.get("/stock-groups")
async def list_stock_groups(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                            from_date: Optional[str] = None, to_date: Optional[str] = None,
                            tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await _list_response(COLL["stock-groups"], tenant, q=q, search_fields=["name"],
                                page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/stock-groups")
async def create_stock_group(payload: StockGroup, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["stock-groups"], payload.model_dump(), tenant, user,
                                unique_fields=["name"], parent_field="parent_group_id")


@router.put("/stock-groups/{item_id}")
async def update_stock_group(item_id: str, payload: StockGroupUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["stock-groups"], item_id, _clean(payload), tenant, user,
                                unique_fields=["name"], parent_field="parent_group_id")


@router.delete("/stock-groups/{item_id}")
async def delete_stock_group(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["stock-groups"], item_id, tenant, user, child_parent_field="parent_group_id")


# ════════════════════════ Inventory: Stock Category (tree) ════════════════════════

@router.get("/stock-categories")
async def list_stock_categories(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                                from_date: Optional[str] = None, to_date: Optional[str] = None,
                                tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await _list_response(COLL["stock-categories"], tenant, q=q, search_fields=["name"],
                                page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/stock-categories")
async def create_stock_category(payload: StockCategory, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["stock-categories"], payload.model_dump(), tenant, user,
                                unique_fields=["name"], parent_field="parent_category_id")


@router.put("/stock-categories/{item_id}")
async def update_stock_category(item_id: str, payload: StockCategoryUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["stock-categories"], item_id, _clean(payload), tenant, user,
                                unique_fields=["name"], parent_field="parent_category_id")


@router.delete("/stock-categories/{item_id}")
async def delete_stock_category(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["stock-categories"], item_id, tenant, user, child_parent_field="parent_category_id")


# ════════════════════════ Inventory: Unit ════════════════════════

@router.get("/units")
async def list_units(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                     from_date: Optional[str] = None, to_date: Optional[str] = None,
                     tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await _list_response(COLL["units"], tenant, q=q, search_fields=["symbol", "formal_name"],
                                sort_field="symbol", page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/units")
async def create_unit(payload: Unit, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = payload.model_dump()
    _validate_unit(data)
    if data.get("base_unit_id"):
        await _ensure_ref(COLL["units"], data["base_unit_id"], tenant, "base_unit_id")
    return await masters_create(COLL["units"], data, tenant, user, unique_fields=["symbol"])


@router.put("/units/{item_id}")
async def update_unit(item_id: str, payload: UnitUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = _clean(payload)
    if data.get("base_unit_id"):
        if data["base_unit_id"] == item_id:
            raise HTTPException(400, "A unit cannot be its own base unit")
        await _ensure_ref(COLL["units"], data["base_unit_id"], tenant, "base_unit_id")
    return await masters_update(COLL["units"], item_id, data, tenant, user, unique_fields=["symbol"])


@router.delete("/units/{item_id}")
async def delete_unit(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["units"], item_id, tenant, user, child_parent_field="base_unit_id")


# ════════════════════════ Inventory: Stock Item ════════════════════════

@router.get("/stock-items")
async def list_stock_items(q: Optional[str] = None, stock_group_id: Optional[str] = None,
                           page: Optional[int] = None, limit: Optional[int] = None,
                           from_date: Optional[str] = None, to_date: Optional[str] = None,
                           tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    extra = {"stock_group_id": stock_group_id} if stock_group_id else None
    return await _list_response(COLL["stock-items"], tenant, q=q, search_fields=["name", "hsn_sac"],
                                extra=extra, page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/stock-items")
async def create_stock_item(payload: StockItem, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = payload.model_dump()
    await _ensure_ref(COLL["units"], data["base_unit_id"], tenant, "base_unit_id")
    if data.get("stock_group_id"):
        await _ensure_ref(COLL["stock-groups"], data["stock_group_id"], tenant, "stock_group_id")
    if data.get("category_id"):
        await _ensure_ref(COLL["stock-categories"], data["category_id"], tenant, "category_id")
    if data.get("alternate_unit"):
        await _ensure_ref(COLL["units"], data["alternate_unit"]["unit_id"], tenant, "alternate_unit.unit_id")
    return await masters_create(COLL["stock-items"], data, tenant, user, unique_fields=["name"])


@router.put("/stock-items/{item_id}")
async def update_stock_item(item_id: str, payload: StockItemUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    data = _clean(payload)
    if data.get("base_unit_id"):
        await _ensure_ref(COLL["units"], data["base_unit_id"], tenant, "base_unit_id")
    if data.get("stock_group_id"):
        await _ensure_ref(COLL["stock-groups"], data["stock_group_id"], tenant, "stock_group_id")
    if data.get("category_id"):
        await _ensure_ref(COLL["stock-categories"], data["category_id"], tenant, "category_id")
    return await masters_update(COLL["stock-items"], item_id, data, tenant, user, unique_fields=["name"])


@router.delete("/stock-items/{item_id}")
async def delete_stock_item(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["stock-items"], item_id, tenant, user)


# ════════════════════════ Inventory: Location (tree) ════════════════════════

@router.get("/locations")
async def list_locations(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                         from_date: Optional[str] = None, to_date: Optional[str] = None,
                         tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await _list_response(COLL["locations"], tenant, q=q, search_fields=["name"],
                                page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/locations")
async def create_location(payload: Location, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["locations"], payload.model_dump(), tenant, user,
                                unique_fields=["name"], parent_field="parent_location_id")


@router.put("/locations/{item_id}")
async def update_location(item_id: str, payload: LocationUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["locations"], item_id, _clean(payload), tenant, user,
                                unique_fields=["name"], parent_field="parent_location_id")


@router.delete("/locations/{item_id}")
async def delete_location(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["locations"], item_id, tenant, user, child_parent_field="parent_location_id")


# ════════════════════════ Statutory: GST Registration ════════════════════════

@router.get("/gst-registrations")
async def list_gst_registrations(q: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_list(COLL["gst-registrations"], tenant, q=q, search_fields=["gstin", "state"], sort_field="gstin")


@router.post("/gst-registrations")
async def create_gst_registration(payload: GstRegistration, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["gst-registrations"], payload.model_dump(), tenant, user, unique_fields=["gstin"])


@router.put("/gst-registrations/{item_id}")
async def update_gst_registration(item_id: str, payload: GstRegistrationUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["gst-registrations"], item_id, _clean(payload), tenant, user, unique_fields=["gstin"])


@router.delete("/gst-registrations/{item_id}")
async def delete_gst_registration(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["gst-registrations"], item_id, tenant, user)


# ════════════════════════ Statutory: GST Classification ════════════════════════

@router.get("/gst-classifications")
async def list_gst_classifications(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                                   from_date: Optional[str] = None, to_date: Optional[str] = None,
                                   tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await _list_response(COLL["gst-classifications"], tenant, q=q, search_fields=["name", "hsn_sac"],
                                page=page, limit=limit, from_date=from_date, to_date=to_date)


@router.post("/gst-classifications")
async def create_gst_classification(payload: GstClassification, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["gst-classifications"], payload.model_dump(), tenant, user, unique_fields=["name"])


@router.put("/gst-classifications/{item_id}")
async def update_gst_classification(item_id: str, payload: GstClassificationUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["gst-classifications"], item_id, _clean(payload), tenant, user, unique_fields=["name"])


@router.delete("/gst-classifications/{item_id}")
async def delete_gst_classification(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["gst-classifications"], item_id, tenant, user)


# ════════════════════════ Statutory: TDS Nature of Payment ════════════════════════

@router.get("/tds-nature-of-payment")
async def list_tds_nop(q: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_list(COLL["tds-nature-of-payment"], tenant, q=q,
                              search_fields=["section_code", "description"], sort_field="section_code")


@router.post("/tds-nature-of-payment")
async def create_tds_nop(payload: TdsNatureOfPayment, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["tds-nature-of-payment"], payload.model_dump(), tenant, user, unique_fields=["section_code"])


@router.put("/tds-nature-of-payment/{item_id}")
async def update_tds_nop(item_id: str, payload: TdsNatureOfPaymentUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["tds-nature-of-payment"], item_id, _clean(payload), tenant, user, unique_fields=["section_code"])


@router.delete("/tds-nature-of-payment/{item_id}")
async def delete_tds_nop(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["tds-nature-of-payment"], item_id, tenant, user)


# ════════════════════════ Statutory: TCS Nature of Goods ════════════════════════

@router.get("/tcs-nature-of-goods")
async def list_tcs_nog(q: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_list(COLL["tcs-nature-of-goods"], tenant, q=q,
                              search_fields=["nature_code", "description"], sort_field="nature_code")


@router.post("/tcs-nature-of-goods")
async def create_tcs_nog(payload: TcsNatureOfGoods, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_create(COLL["tcs-nature-of-goods"], payload.model_dump(), tenant, user, unique_fields=["nature_code"])


@router.put("/tcs-nature-of-goods/{item_id}")
async def update_tcs_nog(item_id: str, payload: TcsNatureOfGoodsUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_update(COLL["tcs-nature-of-goods"], item_id, _clean(payload), tenant, user, unique_fields=["nature_code"])


@router.delete("/tcs-nature-of-goods/{item_id}")
async def delete_tcs_nog(item_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await masters_soft_delete(COLL["tcs-nature-of-goods"], item_id, tenant, user)


# ════════════════════════ Statutory Details — singletons (get + upsert only) ════════════════════════

@router.get("/company-gst-details")
async def get_company_gst_details(tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_get(SINGLETON_COLL["company-gst-details"], tenant)


@router.put("/company-gst-details")
async def upsert_company_gst_details(payload: CompanyGstDetails, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_upsert(SINGLETON_COLL["company-gst-details"], _clean(payload), tenant, user)


@router.get("/tds-details")
async def get_tds_details(tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_get(SINGLETON_COLL["tds-details"], tenant)


@router.put("/tds-details")
async def upsert_tds_details(payload: TdsDetails, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_upsert(SINGLETON_COLL["tds-details"], _clean(payload), tenant, user)


@router.get("/tcs-details")
async def get_tcs_details(tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_get(SINGLETON_COLL["tcs-details"], tenant)


@router.put("/tcs-details")
async def upsert_tcs_details(payload: TcsDetails, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_upsert(SINGLETON_COLL["tcs-details"], _clean(payload), tenant, user)


@router.get("/pan-cin-details")
async def get_pan_cin_details(tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_get(SINGLETON_COLL["pan-cin-details"], tenant)


@router.put("/pan-cin-details")
async def upsert_pan_cin_details(payload: PanCinDetails, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_masters(user)
    return await singleton_upsert(SINGLETON_COLL["pan-cin-details"], _clean(payload), tenant, user)


# ───────────────────────── shared validators ─────────────────────────

async def _ensure_ref(collection: str, ref_id: str, tenant: str, field: str):
    """Validate a foreign reference exists in the same tenant (and isn't deleted)."""
    if not ref_id:
        raise HTTPException(400, f"{field} is required")
    found = await db[collection].find_one(tenant_filter(tenant, {"id": ref_id}), {"_id": 0, "id": 1})
    if not found:
        raise HTTPException(400, f"Referenced {field} not found in this tenant")


async def _ensure_coa_account(account_id: str):
    """Validate a chart_of_accounts row exists. Not tenant-scoped: routers/accounting.py
    itself never filters chart_of_accounts by tenant (single-tenant deployment)."""
    if not account_id:
        raise HTTPException(400, "coa_account_id is required")
    found = await db.chart_of_accounts.find_one({"id": account_id}, {"_id": 0, "id": 1})
    if not found:
        raise HTTPException(400, "Referenced Chart of Accounts entry not found")


async def _ensure_single_base_currency(tenant: str, exclude_id: Optional[str]):
    extra: dict = {"is_base_currency": True}
    if exclude_id:
        extra["id"] = {"$ne": exclude_id}
    existing = await db[COLL["currencies"]].find_one(tenant_filter(tenant, extra), {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(400, "A base currency already exists for this tenant")


def _validate_unit(data: dict):
    if data.get("type") == "compound":
        if not data.get("base_unit_id") or not data.get("conversion_factor"):
            raise HTTPException(400, "A compound unit requires base_unit_id and conversion_factor")


async def create_masters_indexes(database):
    """Compound (tenant_id, ...) indexes — tenant_id first — on every masters
    collection. Called from server startup. Idempotent (create_index is a no-op
    if the index already exists)."""
    for coll in COLL.values():
        # Primary lookup: tenant + business id, and the soft-delete filter.
        await database[coll].create_index([("tenant_id", 1), ("id", 1)], unique=True)
        await database[coll].create_index([("tenant_id", 1), ("is_deleted", 1), ("name", 1)])
    # Singletons: one document per tenant — unique on tenant_id alone.
    for coll in SINGLETON_COLL.values():
        await database[coll].create_index([("tenant_id", 1)], unique=True)
