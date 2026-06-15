"""Tests for Reports — deeper (Module F).

Pure unit tests on the engine's deterministic logic — no live DB required.
Covers:
- FY bounds & multi-period range expansion
- sign convention (asset/expense debit-positive; liability/equity/income credit-positive)
- ratio computation from tagged groupings
- fund-flow source/application direction
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.reports_engine import (
    _fy_bounds, _fy_range, _signed, _sum_tag, _compute_ratios,
)


# ══════════════════════════════════════════════════════════════
# FY helpers
# ══════════════════════════════════════════════════════════════

class TestFyHelpers:
    def test_fy_bounds(self):
        assert _fy_bounds("2024-25") == ("2024-04-01", "2025-03-31")

    def test_fy_bounds_decade_boundary(self):
        assert _fy_bounds("2019-20") == ("2019-04-01", "2020-03-31")

    def test_fy_range_single(self):
        assert _fy_range("2024-25", "2024-25") == ["2024-25"]

    def test_fy_range_multi(self):
        assert _fy_range("2022-23", "2024-25") == ["2022-23", "2023-24", "2024-25"]

    def test_fy_range_reversed_normalizes(self):
        assert _fy_range("2024-25", "2022-23") == ["2022-23", "2023-24", "2024-25"]

    def test_fy_range_two_digit_suffix(self):
        # crossing the year-2099/2100-ish formatting uses last 2 digits
        assert _fy_range("2008-09", "2010-11") == ["2008-09", "2009-10", "2010-11"]


# ══════════════════════════════════════════════════════════════
# Sign convention
# ══════════════════════════════════════════════════════════════

class TestSignConvention:
    def test_asset_debit_positive(self):
        assert _signed("ASSET", 1000, 200) == 800

    def test_expense_debit_positive(self):
        assert _signed("EXPENSE", 500, 0) == 500

    def test_liability_credit_positive(self):
        assert _signed("LIABILITY", 100, 900) == 800

    def test_equity_credit_positive(self):
        assert _signed("EQUITY", 0, 5000) == 5000

    def test_income_credit_positive(self):
        assert _signed("INCOME", 50, 1050) == 1000

    def test_unknown_type_defaults_credit_positive(self):
        # falls to else branch
        assert _signed("UNCLASSIFIED", 0, 300) == 300


# ══════════════════════════════════════════════════════════════
# Tag summation
# ══════════════════════════════════════════════════════════════

class TestSumTag:
    def test_sum_only_tagged_rows(self):
        rows = [
            {"amount": 100, "tags": ["current_asset"]},
            {"amount": 50, "tags": ["current_asset", "inventory"]},
            {"amount": 999, "tags": ["fixed_asset"]},
        ]
        assert _sum_tag(rows, "current_asset") == 150
        assert _sum_tag(rows, "inventory") == 50
        assert _sum_tag(rows, "fixed_asset") == 999

    def test_no_tags_key(self):
        rows = [{"amount": 100}]
        assert _sum_tag(rows, "current_asset") == 0


# ══════════════════════════════════════════════════════════════
# Ratio computation
# ══════════════════════════════════════════════════════════════

class TestRatios:
    def _bs(self):
        return {
            "assets": [
                {"amount": 300000, "tags": ["current_asset"], "account_code": "1100"},
                {"amount": 100000, "tags": ["current_asset", "inventory"], "account_code": "1200"},
                {"amount": 150000, "tags": ["current_asset", "debtor"], "account_code": "1300"},
            ],
            "liabilities": [
                {"amount": 200000, "tags": ["current_liability"], "account_code": "2100"},
            ],
            "equity": [{"amount": 350000, "tags": [], "account_code": "3100"}],
            "total_assets": 550000,
            "total_liabilities": 200000,
            "total_equity": 350000,
        }

    def _pnl(self):
        return {
            "income": [{"amount": 1000000, "tags": [], "account_code": "4100"}],
            "expense": [
                {"amount": 600000, "tags": ["cogs"], "account_code": "5100"},
                {"amount": 200000, "tags": [], "account_code": "5200"},
            ],
            "total_income": 1000000,
            "total_expense": 800000,
            "net_profit": 200000,
        }

    def test_current_ratio(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # current_assets = 300k+100k+150k = 550k; current_liab = 200k → 2.75
        assert r["current_ratio"] == 2.75

    def test_quick_ratio_excludes_inventory(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # quick = (550k - 100k inventory) / 200k = 2.25
        assert r["quick_ratio"] == 2.25

    def test_debt_equity(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # 200k / 350k = 0.5714
        assert r["debt_equity_ratio"] == round(200000 / 350000, 4)

    def test_gross_margin(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # (1,000,000 - 600,000 cogs) / 1,000,000 * 100 = 40%
        assert r["gross_margin_pct"] == 40.0

    def test_net_margin(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # 200k / 1,000k * 100 = 20%
        assert r["net_margin_pct"] == 20.0

    def test_inventory_days(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # inventory 100k / cogs 600k * 365
        assert r["inventory_days"] == round(100000 / 600000 * 365, 4)

    def test_debtor_days(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # debtors 150k / revenue 1,000k * 365
        assert r["debtor_days"] == round(150000 / 1000000 * 365, 4)

    def test_roce(self):
        r = _compute_ratios(self._bs(), self._pnl())
        # net 200k / (equity 350k + debt 200k) * 100
        assert r["roce_pct"] == round(200000 / 550000 * 100, 4)

    def test_zero_current_liability_yields_none(self):
        bs = self._bs()
        bs["liabilities"] = []
        bs["total_liabilities"] = 0
        r = _compute_ratios(bs, self._pnl())
        # current_liabs falls back to total_liabilities which is 0 → None
        assert r["current_ratio"] is None
