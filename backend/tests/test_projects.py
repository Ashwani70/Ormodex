"""Tests for Project & Job Costing — Module I.

Pure unit tests on the P&L math — no live DB required.
Covers:
- time-cost (hours × cost_rate)
- billable value (billable hours × rate; uninvoiced filter)
- project P&L (direct + time + overhead, profit, margin)
- budget-vs-actual implied by total_cost
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.projects import _time_cost, _billable_value, _compute_pnl


# ══════════════════════════════════════════════════════════════
# Time cost
# ══════════════════════════════════════════════════════════════

class TestTimeCost:
    def test_basic(self):
        entries = [
            {"hours": 10, "cost_rate": 500},
            {"hours": 5, "cost_rate": 800},
        ]
        # 10*500 + 5*800 = 5000 + 4000 = 9000
        assert _time_cost(entries) == 9000.0

    def test_empty(self):
        assert _time_cost([]) == 0.0

    def test_missing_cost_rate(self):
        assert _time_cost([{"hours": 10}]) == 0.0


# ══════════════════════════════════════════════════════════════
# Billable value
# ══════════════════════════════════════════════════════════════

class TestBillableValue:
    ENTRIES = [
        {"hours": 10, "rate": 1000, "billable": True, "invoiced": False},
        {"hours": 5, "rate": 1200, "billable": True, "invoiced": True},
        {"hours": 8, "rate": 900, "billable": False, "invoiced": False},
    ]

    def test_total_billable(self):
        # only billable: 10*1000 + 5*1200 = 10000 + 6000 = 16000 (non-billable excluded)
        assert _billable_value(self.ENTRIES) == 16000.0

    def test_uninvoiced_only(self):
        # only the first entry is billable AND uninvoiced: 10*1000 = 10000
        assert _billable_value(self.ENTRIES, only_uninvoiced=True) == 10000.0

    def test_non_billable_excluded(self):
        entries = [{"hours": 8, "rate": 900, "billable": False}]
        assert _billable_value(entries) == 0.0


# ══════════════════════════════════════════════════════════════
# Project P&L
# ══════════════════════════════════════════════════════════════

class TestPnl:
    def test_simple_profit_no_overhead(self):
        p = _compute_pnl(tagged_revenue=100000, tagged_direct_cost=40000,
                         time_cost=20000, overhead_pct=0)
        assert p["total_cost"] == 60000
        assert p["profit"] == 40000
        assert p["margin_pct"] == 40.0

    def test_overhead_applied_on_direct_plus_time(self):
        p = _compute_pnl(tagged_revenue=100000, tagged_direct_cost=40000,
                         time_cost=20000, overhead_pct=10)
        # base = 60000; overhead = 6000; total = 66000; profit = 34000
        assert p["overhead"] == 6000
        assert p["total_cost"] == 66000
        assert p["profit"] == 34000

    def test_loss(self):
        p = _compute_pnl(tagged_revenue=50000, tagged_direct_cost=40000,
                         time_cost=20000, overhead_pct=0)
        assert p["profit"] == -10000
        assert p["margin_pct"] == -20.0

    def test_zero_revenue_margin_none(self):
        p = _compute_pnl(tagged_revenue=0, tagged_direct_cost=5000,
                         time_cost=0, overhead_pct=0)
        assert p["margin_pct"] is None
        assert p["profit"] == -5000

    def test_revenue_only(self):
        p = _compute_pnl(tagged_revenue=80000, tagged_direct_cost=0,
                         time_cost=0, overhead_pct=15)
        assert p["total_cost"] == 0
        assert p["profit"] == 80000
        assert p["margin_pct"] == 100.0

    def test_budget_vs_actual_reconciles(self):
        # total_cost is what budget-vs-actual compares against
        p = _compute_pnl(tagged_revenue=0, tagged_direct_cost=30000,
                         time_cost=10000, overhead_pct=20)
        # base 40000, overhead 8000 → total 48000
        budget = 50000
        assert p["total_cost"] == 48000
        remaining = round(budget - p["total_cost"], 2)
        assert remaining == 2000
        assert p["total_cost"] < budget  # under budget
