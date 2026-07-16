"""Tests for Branch / Multi-location — Module L.

Pure unit tests — no live DB. Covers:
- inter-branch GST: inter-state → IGST, intra-state → CGST+SGST
- e-way bill threshold (₹50,000)
- branch access-control scoping (user_branch_scope, assert_branch_allowed)
"""
import os
import sys

os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from routers.branches import (
    compute_transfer_gst, eway_bill_required,
    user_branch_scope, assert_branch_allowed,
)


# ══════════════════════════════════════════════════════════════
# Inter-branch GST
# ══════════════════════════════════════════════════════════════

class TestTransferGst:
    ITEMS = [{"item_id": "A", "qty": 10, "rate": 1000, "gst_rate": 18}]  # taxable 10,000

    def test_interstate_uses_igst(self):
        # MH (27) → KA (29) = inter-state
        g = compute_transfer_gst(self.ITEMS, "27", "29")
        assert g["is_interstate"] is True
        assert g["igst"] == 1800.0
        assert g["cgst"] == 0.0
        assert g["sgst"] == 0.0
        assert g["invoice_value"] == 11800.0

    def test_intrastate_splits_cgst_sgst(self):
        # MH (27) → MH (27) = intra-state
        g = compute_transfer_gst(self.ITEMS, "27", "27")
        assert g["is_interstate"] is False
        assert g["cgst"] == 900.0
        assert g["sgst"] == 900.0
        assert g["igst"] == 0.0
        assert g["invoice_value"] == 11800.0

    def test_missing_state_treated_as_intrastate(self):
        # can't prove inter-state without both states → safe default intra
        g = compute_transfer_gst(self.ITEMS, None, "29")
        assert g["is_interstate"] is False

    def test_multiple_items(self):
        items = [
            {"item_id": "A", "qty": 5, "rate": 1000, "gst_rate": 18},   # 5000 → 900
            {"item_id": "B", "qty": 2, "rate": 500, "gst_rate": 12},    # 1000 → 120
        ]
        g = compute_transfer_gst(items, "27", "29")
        assert g["taxable_value"] == 6000.0
        assert g["igst"] == 1020.0
        assert g["invoice_value"] == 7020.0


# ══════════════════════════════════════════════════════════════
# E-way bill threshold
# ══════════════════════════════════════════════════════════════

class TestEwayBill:
    def test_above_threshold_required(self):
        assert eway_bill_required(50001, True, 100) is True

    def test_below_threshold_not_required(self):
        assert eway_bill_required(49999, True, 100) is False

    def test_exactly_50k_not_required(self):
        # rule is strictly > 50,000
        assert eway_bill_required(50000, False, 10) is False

    def test_high_value(self):
        assert eway_bill_required(1180000, True, 500) is True


# ══════════════════════════════════════════════════════════════
# Branch access control
# ══════════════════════════════════════════════════════════════

class TestBranchScope:
    def test_admin_sees_all(self):
        assert user_branch_scope({"role": "admin"}) is None

    def test_restricted_user(self):
        assert user_branch_scope({"role": "accountant", "branch_ids": ["B1", "B2"]}) == ["B1", "B2"]

    def test_unrestricted_non_admin(self):
        # no branch_ids → None (all branches)
        assert user_branch_scope({"role": "accountant"}) is None

    def test_assert_allowed_in_scope(self):
        assert_branch_allowed("B1", {"role": "accountant", "branch_ids": ["B1", "B2"]})  # no raise

    def test_assert_denied_out_of_scope(self):
        with pytest.raises(HTTPException) as exc:
            assert_branch_allowed("B9", {"role": "accountant", "branch_ids": ["B1", "B2"]})
        assert exc.value.status_code == 403

    def test_admin_allowed_any_branch(self):
        assert_branch_allowed("B9", {"role": "admin"})  # no raise

    def test_none_branch_allowed(self):
        # a doc without a branch (org-wide) is allowed
        assert_branch_allowed(None, {"role": "accountant", "branch_ids": ["B1"]})
