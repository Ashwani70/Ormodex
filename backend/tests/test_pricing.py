"""Tests for Pricing & Schemes — Module G.

Pure unit tests on the deterministic pricing logic — no live DB required.
Covers:
- price-list item selection (min_qty volume tier)
- date-window validity
- slab boundary selection (correct tier at boundary quantities)
- scheme applicability (item / group / all)
- benefit computation: flat, slab (pct & amount), free_qty
- window helper
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.pricing import (
    _within_window, _pick_list_item, _slab_for_qty,
    _scheme_applies, _compute_scheme_benefit,
)


# ══════════════════════════════════════════════════════════════
# Date-window validity
# ══════════════════════════════════════════════════════════════

class TestWindow:
    def test_no_bounds_always_valid(self):
        assert _within_window(None, None, "2024-06-14") is True

    def test_before_from(self):
        assert _within_window("2024-07-01", None, "2024-06-14") is False

    def test_after_to(self):
        assert _within_window(None, "2024-06-01", "2024-06-14") is False

    def test_inside(self):
        assert _within_window("2024-01-01", "2024-12-31", "2024-06-14") is True

    def test_on_from_boundary(self):
        assert _within_window("2024-06-14", None, "2024-06-14") is True

    def test_on_to_boundary(self):
        assert _within_window(None, "2024-06-14", "2024-06-14") is True


# ══════════════════════════════════════════════════════════════
# Price-list item selection
# ══════════════════════════════════════════════════════════════

class TestPickListItem:
    PL = {"items": [
        {"item_id": "A", "uom": "pcs", "rate": 100, "min_qty": 0},
        {"item_id": "A", "uom": "pcs", "rate": 90, "min_qty": 50},
        {"item_id": "A", "uom": "pcs", "rate": 80, "min_qty": 100},
        {"item_id": "B", "uom": "pcs", "rate": 200, "min_qty": 0},
    ]}

    def test_picks_base_tier_low_qty(self):
        assert _pick_list_item(self.PL, "A", 10)["rate"] == 100

    def test_picks_mid_tier_at_boundary(self):
        # exactly 50 qualifies for the 50-tier
        assert _pick_list_item(self.PL, "A", 50)["rate"] == 90

    def test_picks_top_tier(self):
        assert _pick_list_item(self.PL, "A", 150)["rate"] == 80

    def test_picks_highest_qualifying_tier(self):
        # 99 qualifies for 50-tier but not 100-tier
        assert _pick_list_item(self.PL, "A", 99)["rate"] == 90

    def test_other_item(self):
        assert _pick_list_item(self.PL, "B", 5)["rate"] == 200

    def test_missing_item_returns_none(self):
        assert _pick_list_item(self.PL, "Z", 5) is None


# ══════════════════════════════════════════════════════════════
# Slab boundary selection
# ══════════════════════════════════════════════════════════════

class TestSlabForQty:
    SCHEME = {"slabs": [
        {"from_qty": 0, "to_qty": 9, "discount_pct": 0},
        {"from_qty": 10, "to_qty": 49, "discount_pct": 5},
        {"from_qty": 50, "to_qty": 99, "discount_pct": 10},
        {"from_qty": 100, "to_qty": None, "discount_pct": 15},
    ]}

    def test_low_band(self):
        assert _slab_for_qty(self.SCHEME, 5)["discount_pct"] == 0

    def test_at_lower_boundary_of_band(self):
        # exactly 10 → 5% band (from_qty inclusive)
        assert _slab_for_qty(self.SCHEME, 10)["discount_pct"] == 5

    def test_at_upper_boundary_of_band(self):
        # exactly 49 → still 5% band (to_qty inclusive)
        assert _slab_for_qty(self.SCHEME, 49)["discount_pct"] == 5

    def test_just_over_boundary(self):
        # 50 → next band 10%
        assert _slab_for_qty(self.SCHEME, 50)["discount_pct"] == 10

    def test_open_ended_top_band(self):
        assert _slab_for_qty(self.SCHEME, 1000)["discount_pct"] == 15

    def test_no_matching_slab(self):
        s = {"slabs": [{"from_qty": 100, "to_qty": 200, "discount_pct": 5}]}
        assert _slab_for_qty(s, 5) is None


# ══════════════════════════════════════════════════════════════
# Scheme applicability
# ══════════════════════════════════════════════════════════════

class TestSchemeApplies:
    def test_all(self):
        assert _scheme_applies({"applies_to": "all"}, "ITEM1", None) is True

    def test_item_match(self):
        assert _scheme_applies({"applies_to": "item", "applies_to_id": "ITEM1"}, "ITEM1", None) is True

    def test_item_mismatch(self):
        assert _scheme_applies({"applies_to": "item", "applies_to_id": "ITEM2"}, "ITEM1", None) is False

    def test_group_match(self):
        assert _scheme_applies({"applies_to": "group", "applies_to_id": "G1"}, "ITEM1", "G1") is True

    def test_group_no_customer_group(self):
        assert _scheme_applies({"applies_to": "group", "applies_to_id": "G1"}, "ITEM1", None) is False


# ══════════════════════════════════════════════════════════════
# Benefit computation
# ══════════════════════════════════════════════════════════════

class TestBenefit:
    def test_flat_pct(self):
        scheme = {"name": "Flat10", "type": "flat", "slabs": [{"discount_pct": 10}]}
        b = _compute_scheme_benefit(scheme, base_rate=100, qty=5)
        # line value 500 * 10% = 50
        assert b["discount_amount"] == 50.0
        assert b["free_line"] is None

    def test_flat_amount(self):
        scheme = {"name": "Off25", "type": "flat", "slabs": [{"discount_amount": 25}]}
        b = _compute_scheme_benefit(scheme, base_rate=100, qty=5)
        assert b["discount_amount"] == 25.0

    def test_flat_zero_returns_none(self):
        scheme = {"name": "Nada", "type": "flat", "slabs": [{"discount_pct": 0}]}
        assert _compute_scheme_benefit(scheme, base_rate=100, qty=5) is None

    def test_slab_pct_at_tier(self):
        scheme = {"name": "Vol", "type": "slab", "slabs": [
            {"from_qty": 0, "to_qty": 9, "discount_pct": 0},
            {"from_qty": 10, "to_qty": None, "discount_pct": 8},
        ]}
        b = _compute_scheme_benefit(scheme, base_rate=200, qty=10)
        # qty 10 → 8% of (200*10=2000) = 160
        assert b["discount_amount"] == 160.0

    def test_slab_below_tier_no_discount(self):
        scheme = {"name": "Vol", "type": "slab", "slabs": [
            {"from_qty": 10, "to_qty": None, "discount_pct": 8},
        ]}
        # qty 5 → no slab matches
        assert _compute_scheme_benefit(scheme, base_rate=200, qty=5) is None

    def test_free_qty(self):
        scheme = {"name": "Buy10Get1", "type": "free_qty", "id": "S1", "slabs": [
            {"from_qty": 10, "to_qty": None, "free_item_id": "FREEBIE", "free_qty": 1},
        ]}
        b = _compute_scheme_benefit(scheme, base_rate=100, qty=10)
        assert b["discount_amount"] == 0.0
        assert b["free_line"]["item_id"] == "FREEBIE"
        assert b["free_line"]["qty"] == 1
        assert b["free_line"]["rate"] == 0.0
        assert b["free_line"]["is_free"] is True

    def test_free_qty_below_threshold_none(self):
        scheme = {"name": "Buy10Get1", "type": "free_qty", "slabs": [
            {"from_qty": 10, "to_qty": None, "free_item_id": "FREEBIE", "free_qty": 1},
        ]}
        assert _compute_scheme_benefit(scheme, base_rate=100, qty=5) is None
