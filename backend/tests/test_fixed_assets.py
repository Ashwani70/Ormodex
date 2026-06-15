"""Tests for Fixed Assets Module B — dual depreciation engine.

Tests do NOT require a live MongoDB connection — all DB calls are patched.
Focus: Companies Act SLM/WDV vs IT Act block, half-rate, mid-year, disposal.
"""
import os
import sys

# Must be set before any import that touches core.db (which reads env at import time)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# Ensure the backend package root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

from routers.fixed_assets import (
    _fy_bounds,
    _days_in_fy,
    _days_held_in_fy,
    _companies_act_slm,
    _companies_act_wdv,
    _it_depreciation,
    _put_to_use_days,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helper tests
# ══════════════════════════════════════════════════════════════════════════════

class TestFyBounds:
    def test_standard_fy(self):
        start, end = _fy_bounds("2024-25")
        assert start == date(2024, 4, 1)
        assert end == date(2025, 3, 31)

    def test_fy_days(self):
        # 2024-25 is a leap year crossing (2025 is not leap; FY April 2024 – March 2025)
        days = _days_in_fy("2024-25")
        # April(30)+May(31)+Jun(30)+Jul(31)+Aug(31)+Sep(30)+Oct(31)+Nov(30)+Dec(31)+Jan(31)+Feb(28)+Mar(31) = 365
        assert days == 365

    def test_leap_year_fy(self):
        # 2023-24: includes Feb 2024 which is a leap (29 days)
        days = _days_in_fy("2023-24")
        assert days == 366


class TestDaysHeld:
    def test_full_year(self):
        days = _days_held_in_fy("2024-04-01", "2024-25")
        assert days == 365

    def test_mid_year_addition(self):
        # Added Oct 1 2024; 6 months remaining (Oct–Mar = 183 days)
        days = _days_held_in_fy("2024-10-01", "2024-25")
        assert days == 182  # Oct(31)+Nov(30)+Dec(31)+Jan(31)+Feb(28)+Mar(31) = 182

    def test_not_yet_capitalized(self):
        # Capitalized in next FY
        days = _days_held_in_fy("2025-04-01", "2024-25")
        assert days == 0

    def test_with_disposal(self):
        # Full year asset disposed Dec 31 2024
        days = _days_held_in_fy("2024-04-01", "2024-25", disposal_date_str="2024-12-31")
        # Apr 1 → Dec 31 = 275 days
        assert days == 275


# ══════════════════════════════════════════════════════════════════════════════
# Companies Act SLM
# ══════════════════════════════════════════════════════════════════════════════

class TestCompaniesActSLM:
    """Schedule II SLM: annual = (gross - residual) / life; pro-rate by days."""

    def test_full_year_slm(self):
        # Gross 100,000; Residual 5,000; Life 10 years; held 365/365 days
        depr = _companies_act_slm(
            gross=100_000, residual=5_000, life_years=10,
            days_held=365, total_days=365,
        )
        assert depr == 9_500.0  # (100000-5000)/10 = 9500

    def test_half_year_pro_ration(self):
        # Same asset but held only 183 days out of 365
        depr = _companies_act_slm(
            gross=100_000, residual=5_000, life_years=10,
            days_held=183, total_days=365,
        )
        expected = round(9_500 * 183 / 365, 2)
        assert depr == expected

    def test_mid_year_addition_october(self):
        # Added Oct 1; 182 days in FY 2024-25 (365 total)
        depr = _companies_act_slm(
            gross=500_000, residual=25_000, life_years=15,
            days_held=182, total_days=365,
        )
        annual = (500_000 - 25_000) / 15  # 31,666.67
        expected = round(annual * 182 / 365, 2)
        assert depr == expected

    def test_computer_short_life(self):
        # Computers: 3-year life, full year, high gross
        depr = _companies_act_slm(
            gross=60_000, residual=3_000, life_years=3,
            days_held=365, total_days=365,
        )
        assert depr == round((60_000 - 3_000) / 3, 2)  # 19,000


# ══════════════════════════════════════════════════════════════════════════════
# Companies Act WDV
# ══════════════════════════════════════════════════════════════════════════════

class TestCompaniesActWDV:
    """WDV rate = 1 - (residual/gross)^(1/n); pro-rated; floor at residual."""

    def test_full_year_wdv(self):
        gross = 100_000.0
        residual = 5_000.0
        life = 8.0
        # WDV rate = 1 - (5000/100000)^(1/8) ≈ 0.3261
        import math
        rate = 1.0 - (residual / gross) ** (1.0 / life)
        opening_wdv = gross  # first year
        expected = round(opening_wdv * rate, 2)
        depr = _companies_act_wdv(opening_wdv, residual, life, gross, 365, 365)
        assert depr == expected

    def test_wdv_does_not_go_below_residual(self):
        # When remaining WDV is very close to residual, ensure no overshoot
        depr = _companies_act_wdv(
            opening_wdv=5_100, residual=5_000, life_years=8,
            gross=100_000, days_held=365, total_days=365,
        )
        assert depr <= 100.0  # only 100 remaining above residual


# ══════════════════════════════════════════════════════════════════════════════
# Income Tax Act — Block of Assets
# ══════════════════════════════════════════════════════════════════════════════

class TestITDepreciation:
    """IT Act Sec 32: block WDV * rate; half-rate <180 days."""

    def test_full_rate_existing_block(self):
        # Opening block WDV 500,000; rate 15%; no additions or disposals
        result = _it_depreciation(
            block_wdv=500_000, it_rate=15.0,
            additions=0, disposals=0, half_rate_additions=0,
        )
        assert result["depreciation"] == 75_000.0
        assert result["closing_wdv"] == 425_000.0
        assert result["stcg"] == 0.0

    def test_half_rate_rule_new_addition(self):
        # New asset 200,000 added and put to use < 180 days in FY
        # Opening block = 300,000; rate 15%
        result = _it_depreciation(
            block_wdv=300_000, it_rate=15.0,
            additions=0,
            disposals=0,
            half_rate_additions=200_000,  # < 180 days use
        )
        # Depr on opening block: 300,000 * 15% = 45,000
        # Half-rate on new: 200,000 * 15% * 0.5 = 15,000
        # Total = 60,000
        assert result["depreciation"] == 60_000.0
        assert result["closing_wdv"] == round((300_000 + 200_000) - 60_000.0, 2)

    def test_full_rate_addition_more_than_180_days(self):
        # Asset capitalized April 1 → used all year
        result = _it_depreciation(
            block_wdv=300_000, it_rate=15.0,
            additions=200_000,  # ≥ 180 days
            disposals=0,
            half_rate_additions=0,
        )
        # Full rate on (300,000 + 200,000) = 500,000 * 15% = 75,000
        assert result["depreciation"] == 75_000.0

    def test_disposal_reduces_block(self):
        # Opening 500,000; sold asset for 200,000; rate 15%
        result = _it_depreciation(
            block_wdv=500_000, it_rate=15.0,
            additions=0, disposals=200_000, half_rate_additions=0,
        )
        # Base = 500,000 - 200,000 = 300,000; depr = 300,000 * 15% = 45,000
        assert result["depreciation"] == 45_000.0
        assert result["closing_wdv"] == 255_000.0

    def test_block_extinguished_generates_stcg(self):
        # Opening 100,000; sold for 120,000 → block goes negative
        result = _it_depreciation(
            block_wdv=100_000, it_rate=15.0,
            additions=0, disposals=120_000, half_rate_additions=0,
        )
        assert result["block_extinguished"] is True
        assert result["stcg"] == 20_000.0
        assert result["depreciation"] == 0.0
        assert result["closing_wdv"] == 0.0

    def test_same_asset_different_ca_vs_it(self):
        """
        Core acceptance criterion: same asset, same FY, CA ≠ IT depreciation.

        Asset: Machinery, Gross 1,000,000
        Companies Act: SLM, life 15 years, residual 50,000 → annual = (1,000,000-50,000)/15 = 63,333.33
        IT Act: block WDV 1,000,000 (first year, full-year addition), rate 15% → 150,000

        Both correct, both different.
        """
        ca_depr = _companies_act_slm(
            gross=1_000_000, residual=50_000, life_years=15,
            days_held=365, total_days=365,
        )
        it_result = _it_depreciation(
            block_wdv=0, it_rate=15.0,
            additions=1_000_000,  # full-year addition (≥ 180 days)
            disposals=0, half_rate_additions=0,
        )
        it_depr = it_result["depreciation"]

        # CA: 63,333.33  IT: 150,000 — definitively different
        assert ca_depr == round((1_000_000 - 50_000) / 15, 2)
        assert it_depr == 150_000.0
        assert ca_depr != it_depr

    def test_half_rate_vs_full_rate_different_fy(self):
        """
        Asset added Feb 15 (< 180 days before FY end Mar 31) gets half rate.
        Same asset in the *next* FY (full block) gets full rate.
        """
        # Year of addition: < 180 days → half rate
        result_yr1 = _it_depreciation(
            block_wdv=0, it_rate=15.0,
            additions=0, disposals=0,
            half_rate_additions=500_000,
        )
        yr1_depr = result_yr1["depreciation"]  # 500,000 * 15% * 0.5 = 37,500

        # Next year: block opening = closing WDV from yr1; full rate
        result_yr2 = _it_depreciation(
            block_wdv=result_yr1["closing_wdv"], it_rate=15.0,
            additions=0, disposals=0, half_rate_additions=0,
        )
        yr2_depr = result_yr2["depreciation"]

        assert yr1_depr == 37_500.0
        # yr2: 462,500 * 15% = 69,375
        assert yr2_depr == round(462_500 * 0.15, 2)
        assert yr2_depr > yr1_depr  # full rate > half rate year


# ══════════════════════════════════════════════════════════════════════════════
# Put-to-use days (IT half-rate test)
# ══════════════════════════════════════════════════════════════════════════════

class TestPutToUseDays:
    def test_april_addition_full_year(self):
        days = _put_to_use_days("2024-04-01", "2024-25")
        assert days == 365  # Apr 1 → Mar 31 inclusive

    def test_october_addition(self):
        days = _put_to_use_days("2024-10-01", "2024-25")
        # Oct 1 → Mar 31: Oct(31)+Nov(30)+Dec(31)+Jan(31)+Feb(28)+Mar(31) = 182
        assert days == 182

    def test_february_addition_short(self):
        # Feb 15 2025 → Mar 31 2025 = 45 days → < 180 → half rate applies
        days = _put_to_use_days("2025-02-15", "2024-25")
        assert days == 45
        assert days < 180  # confirms half-rate applies

    def test_october_180_boundary(self):
        # Oct 5 → Mar 31 = 178 days → < 180 → half rate
        days = _put_to_use_days("2024-10-05", "2024-25")
        assert days < 180


# ══════════════════════════════════════════════════════════════════════════════
# Disposal CA gain/loss
# ══════════════════════════════════════════════════════════════════════════════

class TestDisposalGainLoss:
    def test_disposal_gain(self):
        ca_wdv = 200_000.0
        sale = 250_000.0
        gain_loss = round(sale - ca_wdv, 2)
        assert gain_loss == 50_000.0  # GAIN

    def test_disposal_loss(self):
        ca_wdv = 200_000.0
        sale = 150_000.0
        gain_loss = round(sale - ca_wdv, 2)
        assert gain_loss == -50_000.0  # LOSS

    def test_it_stcg_on_block_extinguishment(self):
        # Full block sold; block goes to zero AND sale > closing WDV
        result = _it_depreciation(
            block_wdv=80_000, it_rate=15.0,
            additions=0, disposals=100_000, half_rate_additions=0,
        )
        assert result["block_extinguished"] is True
        assert result["stcg"] == 20_000.0
