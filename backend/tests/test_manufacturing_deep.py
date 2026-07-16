"""
Tests for Manufacturing (deep) module.

Covers:
- 3-level BOM explosion with scrap% applied at each level
- Cyclic BOM detection
- Work-order completion: stock movements (consumed down, FG up, net correct)
- Production Journal posting
- Wastage entry logging (NORMAL vs ABNORMAL)
- ITC-04 period statement: challan listing + scrap reconciliation
- Return-window / overdue flagging on challans

These tests use mongomock or an async in-memory substitute via monkeypatching
so they do not require a live MongoDB instance.  Where transaction semantics
are exercised the test validates the final state rather than the transaction
wrapper itself (mongomock doesn't support multi-document transactions).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bom(fg_id, components, output_qty=1.0, bom_id=None, co_products=None, by_products=None):
    return {
        "id": bom_id or f"bom_{fg_id}",
        "finished_product_id": fg_id,
        "finished_product_name": f"Product {fg_id}",
        "output_qty": output_qty,
        "status": "ACTIVE",
        "components": components,
        "co_products": co_products or [],
        "by_products": by_products or [],
        "items": [],
    }


def _comp(item_id, qty_per, scrap_pct=0.0, uom="pcs"):
    return {
        "component_item_id": item_id,
        "component_item_name": f"Item {item_id}",
        "qty_per": qty_per,
        "uom": uom,
        "scrap_pct": scrap_pct,
        "is_optional": False,
    }


def _prod(item_id, quantity=100.0, cost_price=10.0):
    return {"id": item_id, "name": f"Item {item_id}", "quantity": quantity, "cost_price": cost_price}


# ─────────────────────────────────────────────────────────────────────────────
# BOM Explosion Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBomExplosion:
    """Tests for the _explode_bom recursive function."""

    @pytest.mark.asyncio
    async def test_single_level_no_scrap(self):
        """1 BOM level, no scrap → required qty == qty_per × target_qty."""
        from routers.manufacturing import _explode_bom

        bom = _bom("FG1", [_comp("RM1", qty_per=2.0), _comp("RM2", qty_per=3.0)])

        async def fake_resolve(item_id, bom_index=None):
            return None  # raw materials — no sub-BOM

        with patch("routers.manufacturing._resolve_bom_for_item", side_effect=fake_resolve):
            result = await _explode_bom(bom, target_qty=10.0, ancestor_ids={"FG1"})

        assert abs(result["RM1"]["required_qty"] - 20.0) < 1e-6
        assert abs(result["RM2"]["required_qty"] - 30.0) < 1e-6

    @pytest.mark.asyncio
    async def test_single_level_with_scrap(self):
        """Scrap % increases gross requirement correctly."""
        from routers.manufacturing import _explode_bom

        # qty_per=4, scrap_pct=25 → gross = 4 * 1.25 = 5 per FG unit
        bom = _bom("FG1", [_comp("RM1", qty_per=4.0, scrap_pct=25.0)])

        with patch("routers.manufacturing._resolve_bom_for_item", return_value=None):
            result = await _explode_bom(bom, target_qty=5.0, ancestor_ids={"FG1"})

        # 4 * 1.25 * 5 = 25
        assert abs(result["RM1"]["required_qty"] - 25.0) < 1e-6

    @pytest.mark.asyncio
    async def test_three_level_explosion_with_scrap(self):
        """
        3-level BOM:
          FG  (output=1) needs 2 × SA1 (sub-assembly)
          SA1 (output=1) needs 3 × RM1 (scrap 10%)  +  1 × RM2
          RM1/RM2 are raw materials

        Target qty = 4 FG units.
        Expected:
          SA1 needed = 2 * 4 = 8 units of SA1
          RM1 needed = 3 * 1.10 * 8 = 26.4
          RM2 needed = 1 * 8 = 8
        """
        from routers.manufacturing import _explode_bom

        bom_fg = _bom("FG", [_comp("SA1", qty_per=2.0, scrap_pct=0.0)], bom_id="bom_FG")
        bom_sa1 = _bom("SA1", [_comp("RM1", qty_per=3.0, scrap_pct=10.0), _comp("RM2", qty_per=1.0)], bom_id="bom_SA1")

        async def fake_resolve(item_id, bom_index=None):
            if item_id == "SA1":
                return bom_sa1
            return None

        with patch("routers.manufacturing._resolve_bom_for_item", side_effect=fake_resolve):
            result = await _explode_bom(bom_fg, target_qty=4.0, ancestor_ids={"FG"})

        assert abs(result["RM1"]["required_qty"] - 26.4) < 1e-5
        assert abs(result["RM2"]["required_qty"] - 8.0) < 1e-6
        # SA1 is NOT in result (it was exploded into RM1/RM2)
        assert "SA1" not in result

    @pytest.mark.asyncio
    async def test_deep_three_levels_scrap_at_each(self):
        """
        3 levels, scrap at every level:
          FG  needs 2 × L2 (scrap=5%)    → gross per FG = 2*1.05=2.1
          L2  needs 4 × L3 (scrap=10%)   → gross per L2 = 4*1.10=4.4
          L3  needs 5 × RM  (scrap=20%)  → gross per L3 = 5*1.20=6.0

        target_qty = 3 FG
        L2 needed = 2.1 * 3 = 6.3
        L3 needed = 4.4 * 6.3 = 27.72
        RM needed = 6.0 * 27.72 = 166.32
        """
        from routers.manufacturing import _explode_bom

        bom_fg = _bom("FG", [_comp("L2", qty_per=2.0, scrap_pct=5.0)])
        bom_l2 = _bom("L2", [_comp("L3", qty_per=4.0, scrap_pct=10.0)])
        bom_l3 = _bom("L3", [_comp("RM", qty_per=5.0, scrap_pct=20.0)])

        async def fake_resolve(item_id, bom_index=None):
            return {"L2": bom_l2, "L3": bom_l3}.get(item_id)

        with patch("routers.manufacturing._resolve_bom_for_item", side_effect=fake_resolve):
            result = await _explode_bom(bom_fg, target_qty=3.0, ancestor_ids={"FG"})

        assert abs(result["RM"]["required_qty"] - 166.32) < 1e-3

    @pytest.mark.asyncio
    async def test_cyclic_bom_direct(self):
        """A BOM where the FG appears as its own component raises HTTPException."""
        from fastapi import HTTPException
        from routers.manufacturing import _explode_bom

        # FG1 → RM1, but ancestor_ids already contains RM1 (simulating FG1 appearing in its own chain)
        bom = _bom("FG1", [_comp("FG1", qty_per=1.0)])  # self-reference

        with pytest.raises(HTTPException) as exc_info:
            await _explode_bom(bom, target_qty=1.0, ancestor_ids={"FG1"})

        assert exc_info.value.status_code == 400
        assert "cyclic" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_cyclic_bom_indirect(self):
        """FG → SA → FG (indirect cycle) raises HTTPException."""
        from fastapi import HTTPException
        from routers.manufacturing import _explode_bom

        bom_fg = _bom("FG", [_comp("SA", qty_per=1.0)])
        bom_sa = _bom("SA", [_comp("FG", qty_per=1.0)])  # refers back to FG → cycle

        async def fake_resolve(item_id, bom_index=None):
            return {"SA": bom_sa}.get(item_id)

        with patch("routers.manufacturing._resolve_bom_for_item", side_effect=fake_resolve):
            with pytest.raises(HTTPException) as exc_info:
                await _explode_bom(bom_fg, target_qty=1.0, ancestor_ids={"FG"})

        assert exc_info.value.status_code == 400
        assert "cyclic" in exc_info.value.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Work Order Completion Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkOrderCompletion:
    """Tests for complete_work_order endpoint stock movements."""

    def _make_db(self, products_by_id, bom_doc, wo_doc):
        """Build a minimal fake db with the shapes needed by complete_work_order."""
        mock_db = MagicMock()

        async def find_one_products(query, *a, **kw):
            pid = query.get("id")
            return dict(products_by_id.get(pid, {}))

        async def find_one_boms(query, *a, **kw):
            return bom_doc if query.get("id") == bom_doc["id"] else None

        async def update_one(*a, **kw):
            pass

        async def insert_one(*a, **kw):
            pass

        mock_db.products.find_one = AsyncMock(side_effect=find_one_products)
        mock_db.products.update_one = AsyncMock(side_effect=update_one)
        mock_db.boms.find_one = AsyncMock(side_effect=find_one_boms)
        mock_db.stock_transactions.insert_one = AsyncMock(side_effect=insert_one)
        mock_db.work_orders.update_one = AsyncMock(side_effect=update_one)
        mock_db.audit_logs.insert_one = AsyncMock(side_effect=insert_one)

        return mock_db

    @pytest.mark.asyncio
    async def test_stock_deducted_and_fg_added(self):
        """
        Completing a WO must:
        - Deduct each component × (qty_per + scrap) × planned_qty from stock
        - Add planned_qty to FG stock
        - Call update_one for each product touched
        """
        bom_doc = _bom(
            "FG1",
            [_comp("RM1", qty_per=2.0, scrap_pct=0.0), _comp("RM2", qty_per=3.0, scrap_pct=10.0)],
            bom_id="bom1",
        )
        wo_doc = {
            "id": "wo1", "bom_id": "bom1", "product_id": "FG1",
            "product_name": "Product FG1", "quantity_planned": 5.0,
            "status": "IN_PROGRESS", "wo_number": "WO-26-00001",
        }
        products = {
            "RM1": _prod("RM1", quantity=50.0),
            "RM2": _prod("RM2", quantity=30.0),
            "FG1": _prod("FG1", quantity=0.0),
        }

        async def fake_find(query, *a, **kw):
            pid = query.get("id")
            p = products.get(pid)
            return dict(p) if p else None

        def fake_find_many(query, *a, **kw):
            ids = query.get("id", {}).get("$in", [])
            class FC:
                async def to_list(self, n):
                    return [dict(products[i]) for i in ids if i in products]
            return FC()

        from fastapi import HTTPException
        import routers.manufacturing as mfg_mod

        # complete_work_order now posts each movement through post_entry
        # (core.stock_ledger) instead of writing products.quantity /
        # stock_transactions directly — assert on the qty/stock_item_id it
        # was called with rather than a raw products.update_one write.
        posted = []

        async def fake_post_entry(*, stock_item_id, godown_id, qty, movement_type, **kw):
            posted.append({"stock_item_id": stock_item_id, "qty": qty, "movement_type": movement_type})
            return {"id": "entry1", "stock_item_id": stock_item_id, "qty": qty, "rate": kw.get("rate") or 0, "value": 0}

        async def fake_resolve_stock_item_ids(product_ids, user=None):
            return {pid: pid for pid in dict.fromkeys(product_ids) if pid}  # 1:1 in this test's fixtures

        async def fake_resolve_godown_id(godown_id):
            return godown_id or "godown1"

        with patch.object(mfg_mod, "db") as mock_db:
            mock_db.products.find_one = AsyncMock(side_effect=fake_find)
            mock_db.products.find = MagicMock(side_effect=fake_find_many)
            mock_db.boms.find_one = AsyncMock(return_value=bom_doc)
            mock_db.work_orders.find_one = AsyncMock(return_value=wo_doc)
            mock_db.work_orders.update_one = AsyncMock()
            mock_db.audit_logs.insert_one = AsyncMock()

            # Monkeypatch crud_get and crud_update to bypass real DB calls
            async def fake_crud_get(collection, item_id):
                if collection == "work_orders":
                    return wo_doc
                raise HTTPException(404)

            async def fake_crud_update(collection, item_id, update, user=None):
                return {**wo_doc, **update}

            with patch.object(mfg_mod, "crud_get", side_effect=fake_crud_get), \
                 patch.object(mfg_mod, "crud_update", side_effect=fake_crud_update), \
                 patch.object(mfg_mod, "post_entry", side_effect=fake_post_entry), \
                 patch.object(mfg_mod, "resolve_stock_item_ids_for_products", side_effect=fake_resolve_stock_item_ids), \
                 patch.object(mfg_mod, "resolve_godown_id", side_effect=fake_resolve_godown_id):
                user = {"id": "u1", "name": "Tester", "role": "admin"}
                result = await mfg_mod.complete_work_order("wo1", user)

        posted_by_item = {p["stock_item_id"]: p["qty"] for p in posted}
        # RM1: 2.0 * 5 = 10 consumed (negative delta)
        assert abs(posted_by_item.get("RM1", 0) - (-10.0)) < 1e-5
        # RM2: 3.0 * 1.10 * 5 = 16.5 consumed (negative delta)
        assert abs(posted_by_item.get("RM2", 0) - (-16.5)) < 1e-5
        # FG1: +5 produced
        assert abs(posted_by_item.get("FG1", 0) - 5.0) < 1e-5

    @pytest.mark.asyncio
    async def test_insufficient_stock_raises_400(self):
        """complete_work_order must raise 400 if any component is short."""
        from fastapi import HTTPException
        import routers.manufacturing as mfg_mod

        bom_doc = _bom("FG1", [_comp("RM1", qty_per=100.0)], bom_id="bom1")
        wo_doc = {
            "id": "wo1", "bom_id": "bom1", "product_id": "FG1",
            "product_name": "FG1", "quantity_planned": 5.0,
            "status": "IN_PROGRESS", "wo_number": "WO-26-00002",
        }
        products = {"RM1": _prod("RM1", quantity=10.0)}  # only 10, need 500

        def fake_find_many(query, *a, **kw):
            ids = query.get("id", {}).get("$in", [])
            class FC:
                async def to_list(self, n):
                    return [dict(products[i]) for i in ids if i in products]
            return FC()

        with patch.object(mfg_mod, "db") as mock_db:
            mock_db.products.find_one = AsyncMock(side_effect=lambda q, *a, **kw: products.get(q["id"]))
            mock_db.products.find = MagicMock(side_effect=fake_find_many)
            mock_db.boms.find_one = AsyncMock(return_value=bom_doc)

            async def fake_crud_get(collection, item_id):
                if collection == "work_orders":
                    return wo_doc
                raise HTTPException(404)

            with patch.object(mfg_mod, "crud_get", side_effect=fake_crud_get):
                user = {"id": "u1", "name": "Tester", "role": "admin"}
                with pytest.raises(HTTPException) as exc_info:
                    await mfg_mod.complete_work_order("wo1", user)

        assert exc_info.value.status_code == 400
        assert "insufficient" in exc_info.value.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Production Journal Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProductionJournal:

    @pytest.mark.asyncio
    async def test_journal_deducts_consumption_adds_output(self):
        """Posting a journal deducts consumed items and adds output items to stock."""
        import routers.manufacturing as mfg_mod
        from routers.manufacturing import ProductionJournal, ConsumptionLine, OutputLine

        wo_doc = {"id": "wo1", "status": "IN_PROGRESS", "wo_number": "WO-26-00001", "product_id": "FG"}
        products = {
            "RM1": {"id": "RM1", "name": "RM1", "quantity": 50.0, "cost_price": 5.0},
            "FG":  {"id": "FG",  "name": "FG",  "quantity": 0.0,  "cost_price": 0.0},
        }

        async def fake_find(query, *a, **kw):
            return dict(products.get(query.get("id"), {})) or None

        def fake_find_many(query, *a, **kw):
            ids = query.get("id", {}).get("$in", [])
            class FC:
                async def to_list(self, n):
                    return [dict(products[i]) for i in ids if i in products]
            return FC()

        payload = ProductionJournal(
            work_order_id="wo1",
            date="2025-06-01",
            consumption=[ConsumptionLine(item_id="RM1", item_name="RM1", qty=20.0)],
            output=[OutputLine(item_id="FG", item_name="FG", qty=4.0)],
        )

        # create_production_journal now posts each movement through
        # post_entry (core.stock_ledger) instead of writing products.quantity
        # / stock_transactions directly — assert on what it was called with.
        posted = []

        async def fake_post_entry(*, stock_item_id, godown_id, qty, movement_type, **kw):
            posted.append({"stock_item_id": stock_item_id, "qty": qty, "movement_type": movement_type})
            return {"id": "entry1", "stock_item_id": stock_item_id, "qty": qty, "rate": kw.get("rate") or 0, "value": 0}

        async def fake_resolve_stock_item_ids(product_ids, user=None):
            return {pid: pid for pid in dict.fromkeys(product_ids) if pid}  # 1:1 in this test's fixtures

        async def fake_resolve_godown_id(godown_id):
            return godown_id or "godown1"

        with patch.object(mfg_mod, "db") as mock_db:
            mock_db.products.find_one = AsyncMock(side_effect=fake_find)
            mock_db.products.find = MagicMock(side_effect=fake_find_many)
            mock_db.work_orders.update_one = AsyncMock()
            mock_db.production_journals.insert_one = AsyncMock()
            mock_db.audit_logs.insert_one = AsyncMock()
            mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})
            async def fake_crud_get(coll, id_):
                return wo_doc

            async def fake_crud_create(coll, doc, user=None):
                return doc

            with patch.object(mfg_mod, "crud_get", side_effect=fake_crud_get), \
                 patch.object(mfg_mod, "crud_create", side_effect=fake_crud_create), \
                 patch.object(mfg_mod, "post_entry", side_effect=fake_post_entry), \
                 patch.object(mfg_mod, "resolve_stock_item_ids_for_products", side_effect=fake_resolve_stock_item_ids), \
                 patch.object(mfg_mod, "resolve_godown_id", side_effect=fake_resolve_godown_id), \
                 patch("routers.manufacturing.next_doc_number", AsyncMock(return_value="PJ-26-00001")):
                user = {"id": "u1", "name": "T", "role": "admin"}
                result = await mfg_mod.create_production_journal(payload, user)

        posted_by_item = {p["stock_item_id"]: p["qty"] for p in posted}
        assert abs(posted_by_item.get("RM1", 0) - (-20.0)) < 1e-6  # consumed
        assert abs(posted_by_item.get("FG", 0) - 4.0) < 1e-6       # produced


# ─────────────────────────────────────────────────────────────────────────────
# Wastage Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWastage:

    @pytest.mark.asyncio
    async def test_normal_wastage_valuation_auto_computed(self):
        """If valuation is 0, it is computed from cost_price * qty."""
        import routers.manufacturing as mfg_mod
        from routers.manufacturing import WastageEntry

        product = {"id": "RM1", "cost_price": 12.5, "quantity": 100.0}

        with patch.object(mfg_mod, "db") as mock_db:
            mock_db.products.find_one = AsyncMock(return_value=product)
            mock_db.wastage_entries.insert_one = AsyncMock()
            mock_db.audit_logs.insert_one = AsyncMock()
            mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})

            saved = {}

            async def fake_create(coll, doc, user=None):
                saved.update(doc)
                return doc

            with patch.object(mfg_mod, "crud_create", side_effect=fake_create):
                with patch("routers.manufacturing.next_doc_number", AsyncMock(return_value="WE-26-00001")):
                    payload = WastageEntry(item_id="RM1", item_name="RM1", qty=8.0, reason_code="NORMAL")
                    user = {"id": "u1", "name": "T", "role": "admin"}
                    await mfg_mod.create_wastage(payload, user)

        assert abs(saved.get("valuation", 0) - 100.0) < 1e-6  # 12.5 * 8

    @pytest.mark.asyncio
    async def test_abnormal_wastage_flagged(self):
        """ABNORMAL reason code is persisted as-is (expense route handled by accounting)."""
        import routers.manufacturing as mfg_mod
        from routers.manufacturing import WastageEntry

        with patch.object(mfg_mod, "db") as mock_db:
            mock_db.products.find_one = AsyncMock(return_value={"id": "RM2", "cost_price": 5.0})
            mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 2})

            saved = {}

            async def fake_create(coll, doc, user=None):
                saved.update(doc)
                return doc

            with patch.object(mfg_mod, "crud_create", side_effect=fake_create):
                with patch("routers.manufacturing.next_doc_number", AsyncMock(return_value="WE-26-00002")):
                    payload = WastageEntry(item_id="RM2", item_name="RM2", qty=3.0, reason_code="ABNORMAL")
                    await mfg_mod.create_wastage(payload, {"id": "u1", "name": "T", "role": "admin"})

        assert saved.get("reason_code") == "ABNORMAL"


# ─────────────────────────────────────────────────────────────────────────────
# ITC-04 Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestItc04:

    def _make_challan(self, cid, date, status="PENDING", job_worker="JW Ltd",
                      qty=10.0, taxable_value=5000.0, due_date=None, is_overdue=False):
        return {
            "id": cid,
            "challan_number": f"JWC-{cid}",
            "date": date,
            "due_date": due_date or "2026-06-01",
            "is_overdue": is_overdue,
            "deemed_supply": is_overdue,
            "job_worker_id": "jw1",
            "job_worker_name": job_worker,
            "nature": "inputs",
            "status": status,
            "items": [{"product_id": "P1", "product_name": "Prod A", "quantity": qty, "unit": "pcs", "taxable_value": taxable_value}],
        }

    def _make_receipt(self, rid, challan_id, date, qty_recv=8.0, scrap=1.0):
        return {
            "id": rid,
            "receipt_number": f"JWR-{rid}",
            "challan_id": challan_id,
            "date": date,
            "items": [{"product_id": "P1", "product_name": "Prod A", "quantity_received": qty_recv, "scrap_quantity": scrap, "unit": "pcs"}],
        }

    @pytest.mark.asyncio
    async def test_itc04_lists_correct_challans(self):
        """ITC-04 for a period returns only challans issued in that period."""
        import routers.job_work as jw_mod

        challan_in = self._make_challan("C1", "2025-06-10", taxable_value=3000.0)
        challan_out = self._make_challan("C2", "2025-05-01", taxable_value=2000.0)  # outside period
        receipt_in = self._make_receipt("R1", "C1", "2025-06-15", qty_recv=8.0, scrap=1.0)

        all_challans = {"C1": challan_in, "C2": challan_out}

        def mock_challan_find(query, *a, **kw):
            # get_itc04 calls job_work_challans.find() twice with different
            # filter shapes: a date-range query for the period itself, and a
            # batched {"id": {"$in": [...]}} lookup (the N+1 fix) to resolve
            # each inward receipt's parent challan for reference/reporting.
            if "id" in query and "$in" in query.get("id", {}):
                ids = query["id"]["$in"]
                results = [all_challans[i] for i in ids if i in all_challans]
            else:
                start = query.get("date", {}).get("$gte", "")
                end = query.get("date", {}).get("$lt", "")
                results = [c for c in [challan_in, challan_out] if start <= c["date"] < end]

            class FakeCursor:
                def __init__(self, data): self._data = data
                def sort(self, *a, **kw): return self
                async def to_list(self, n): return self._data

            return FakeCursor(results)

        def mock_receipt_find(query, *a, **kw):
            start = query.get("date", {}).get("$gte", "")
            end = query.get("date", {}).get("$lt", "")
            results = [r for r in [receipt_in] if start <= r["date"] < end]

            class FakeCursor:
                def __init__(self, data): self._data = data
                def sort(self, *a, **kw): return self
                async def to_list(self, n): return self._data

            return FakeCursor(results)

        with patch.object(jw_mod, "db") as mock_db:
            mock_db.job_work_challans.find = mock_challan_find
            mock_db.job_work_receipts.find = mock_receipt_find
            mock_db.job_work_challans.find_one = AsyncMock(return_value=challan_in)

            user = {"id": "u1", "name": "T", "role": "admin"}
            result = await jw_mod.get_itc04(period="062025", user=user)

        assert result["summary"]["total_challans_issued"] == 1
        assert result["summary"]["total_taxable_value_sent"] == 3000.0
        assert len(result["table4_outward_challans"]) == 1
        assert result["table4_outward_challans"][0]["challan_number"] == "JWC-C1"

    @pytest.mark.asyncio
    async def test_itc04_summary_sent_vs_received(self):
        """ITC-04 summary correctly sums qty sent, received, and scrap."""
        import routers.job_work as jw_mod

        challan = self._make_challan("C1", "2025-06-05", qty=10.0, taxable_value=1000.0)
        receipt = self._make_receipt("R1", "C1", "2025-06-20", qty_recv=7.0, scrap=2.0)

        def mock_challan_find(query, *a, **kw):
            class FC:
                def sort(self, *a, **kw): return self
                async def to_list(self, n): return [challan]
            return FC()

        def mock_receipt_find(query, *a, **kw):
            class FC:
                def sort(self, *a, **kw): return self
                async def to_list(self, n): return [receipt]
            return FC()

        with patch.object(jw_mod, "db") as mock_db:
            mock_db.job_work_challans.find = mock_challan_find
            mock_db.job_work_receipts.find = mock_receipt_find
            mock_db.job_work_challans.find_one = AsyncMock(return_value=challan)

            user = {"id": "u1", "role": "admin"}
            result = await jw_mod.get_itc04(period="062025", user=user)

        s = result["summary"]
        assert abs(s["total_quantity_sent"] - 10.0) < 1e-6
        assert abs(s["total_quantity_received"] - 7.0) < 1e-6
        assert abs(s["total_scrap"] - 2.0) < 1e-6

    @pytest.mark.asyncio
    async def test_itc04_invalid_period_raises_400(self):
        """Non-MMYYYY period raises 400."""
        import routers.job_work as jw_mod
        from fastapi import HTTPException

        user = {"id": "u1", "role": "admin"}
        with pytest.raises(HTTPException) as exc:
            await jw_mod.get_itc04(period="badperiod", user=user)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_overdue_challan_flagged(self):
        """A challan past its due_date is flagged is_overdue=True in the pending report."""
        import routers.job_work as jw_mod

        past_due = (datetime.now(timezone.utc) - timedelta(days=400)).date().isoformat()
        challan = self._make_challan("C1", "2024-01-01", status="PENDING",
                                     qty=10.0, due_date=past_due, is_overdue=True)

        def mock_find(query, *a, **kw):
            class FC:
                async def to_list(self, n): return [challan]
            return FC()

        def mock_receipt_find(query, *a, **kw):
            class FC:
                async def to_list(self, n): return []
            return FC()

        with patch.object(jw_mod, "db") as mock_db:
            mock_db.job_work_challans.find = mock_find
            mock_db.job_work_receipts.find = mock_receipt_find

            user = {"id": "u1", "role": "admin"}
            report = await jw_mod.get_pending_job_work(user=user)

        assert any(r["is_overdue"] for r in report)
        assert any(r["deemed_supply"] for r in report)


# ─────────────────────────────────────────────────────────────────────────────
# Return-window helper tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReturnWindow:

    @pytest.mark.asyncio
    async def test_default_inputs_365_days(self):
        """Without a rate_tables override, inputs window is 365 days."""
        import routers.job_work as jw_mod

        with patch.object(jw_mod, "db") as mock_db:
            mock_db.rate_tables.find_one = AsyncMock(return_value=None)
            days = await jw_mod._get_return_window_days("inputs")

        assert days == 365

    @pytest.mark.asyncio
    async def test_default_capital_goods_1095_days(self):
        """Without a rate_tables override, capital goods window is 1095 days."""
        import routers.job_work as jw_mod

        with patch.object(jw_mod, "db") as mock_db:
            mock_db.rate_tables.find_one = AsyncMock(return_value=None)
            days = await jw_mod._get_return_window_days("capital_goods")

        assert days == 1095

    @pytest.mark.asyncio
    async def test_custom_rate_table_overrides_default(self):
        """Admin-configured rate table value overrides statutory default."""
        import routers.job_work as jw_mod

        with patch.object(jw_mod, "db") as mock_db:
            mock_db.rate_tables.find_one = AsyncMock(return_value={"key": "job_work_return_window_inputs", "value": 180})
            days = await jw_mod._get_return_window_days("inputs")

        assert days == 180

    def test_due_date_calculation(self):
        """_due_date correctly adds window_days to challan date."""
        from routers.job_work import _due_date
        result = _due_date("2025-01-01", 365)
        assert result == "2026-01-01"

    def test_is_overdue_past_date(self):
        """Past due date is flagged as overdue."""
        from routers.job_work import _is_overdue
        assert _is_overdue("2020-01-01") is True

    def test_is_not_overdue_future_date(self):
        """Future due date is not overdue."""
        from routers.job_work import _is_overdue
        future = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        assert _is_overdue(future) is False
