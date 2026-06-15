"""Tests for Payroll Module C — statutory computation engine.

All tests are pure-function unit tests (no DB). Focus:
- PF: employee/employer split, wage ceiling cap
- ESI: gross ceiling, contribution-period rule
- PT: state slab lookup
- TDS: old vs new regime, LOP proration, mid-year declaration change spread
- LOP: proration of gross and statutory bases
- Gratuity: eligibility threshold (5 years), formula
- F&F net payable math
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.payroll import (
    _compute_pf,
    _compute_esi,
    _compute_pt,
    _compute_tds_monthly,
    _apply_lop,
    _compute_gratuity,
    _remaining_months_in_fy,
    _tax_from_slabs,
    _default_tds_slabs,
    _parse_period,
    _period_days,
)

PARAMS = {
    "pf_wage_ceiling": 15000.0,
    "pf_employee_rate": 12.0,
    "pf_employer_epf_rate": 3.67,
    "pf_employer_eps_rate": 8.33,
    "pf_admin_rate": 0.5,
    "esi_wage_ceiling": 21000.0,
    "esi_employee_rate": 0.75,
    "esi_employer_rate": 3.25,
    "standard_deduction": 50000.0,
    "cess_rate": 4.0,
    "pt_state_slabs": {
        "MH": [
            {"min_salary": 0, "max_salary": 7499, "annual_pt": 0},
            {"min_salary": 7500, "max_salary": 9999, "annual_pt": 1800},
            {"min_salary": 10000, "max_salary": None, "annual_pt": 2400},
        ],
        "KA": [
            {"min_salary": 0, "max_salary": 14999, "annual_pt": 0},
            {"min_salary": 15000, "max_salary": None, "annual_pt": 2400},
        ],
        "TN": [
            {"min_salary": 0, "max_salary": None, "annual_pt": 0},
        ],
    },
}


# ══════════════════════════════════════════════════════════════
# PF
# ══════════════════════════════════════════════════════════════

class TestPF:
    def test_pf_below_ceiling(self):
        result = _compute_pf(12000.0, PARAMS)
        assert result["employee_pf"] == 1440.0       # 12000 * 12%
        assert result["employer_epf"] == round(12000 * 0.0367, 2)
        assert result["employer_eps"] == round(12000 * 0.0833, 2)

    def test_pf_at_ceiling(self):
        result = _compute_pf(15000.0, PARAMS)
        assert result["employee_pf"] == 1800.0
        assert result["pf_wages_capped"] == 15000.0

    def test_pf_above_ceiling_capped(self):
        # Gross 50,000 but PF wages capped at 15,000
        result = _compute_pf(50000.0, PARAMS)
        assert result["pf_wages_capped"] == 15000.0
        assert result["employee_pf"] == 1800.0       # still 12% of ceiling only

    def test_employer_pf_epf_eps_split(self):
        result = _compute_pf(15000.0, PARAMS)
        # EPF + EPS must equal 12% of capped wages (within rounding)
        total = result["employer_epf"] + result["employer_eps"]
        assert abs(total - 1800.0) <= 0.02  # rounding tolerance

    def test_pf_zero_wages(self):
        result = _compute_pf(0.0, PARAMS)
        assert result["employee_pf"] == 0.0
        assert result["employer_epf"] == 0.0


# ══════════════════════════════════════════════════════════════
# ESI
# ══════════════════════════════════════════════════════════════

class TestESI:
    def test_esi_below_ceiling(self):
        result = _compute_esi(20000.0, PARAMS, False)
        assert result["esi_applicable"] is True
        assert result["employee_esi"] == round(20000 * 0.0075, 2)
        assert result["employer_esi"] == round(20000 * 0.0325, 2)

    def test_esi_above_ceiling_not_applicable(self):
        result = _compute_esi(22000.0, PARAMS, False)
        assert result["esi_applicable"] is False
        assert result["employee_esi"] == 0.0
        assert result["employer_esi"] == 0.0

    def test_esi_contribution_period_rule(self):
        """Employee crossed ceiling mid-period but in_contribution_period=True → ESI continues."""
        result = _compute_esi(25000.0, PARAMS, in_contribution_period=True)
        assert result["esi_applicable"] is True
        assert result["employee_esi"] == round(25000 * 0.0075, 2)

    def test_esi_at_exactly_ceiling(self):
        result = _compute_esi(21000.0, PARAMS, False)
        assert result["esi_applicable"] is True

    def test_esi_just_above_ceiling_no_period_flag(self):
        result = _compute_esi(21001.0, PARAMS, False)
        assert result["esi_applicable"] is False


# ══════════════════════════════════════════════════════════════
# Professional Tax
# ══════════════════════════════════════════════════════════════

class TestPT:
    def test_pt_mh_below_threshold(self):
        pt = _compute_pt(7000.0, "MH", PARAMS)
        assert pt == 0.0

    def test_pt_mh_mid_slab(self):
        # MH: 7500–9999 → annual 1800 → monthly 150
        pt = _compute_pt(8000.0, "MH", PARAMS)
        assert pt == round(1800 / 12, 2)

    def test_pt_mh_top_slab(self):
        # MH: ≥10000 → annual 2400 → monthly 200
        pt = _compute_pt(15000.0, "MH", PARAMS)
        assert pt == round(2400 / 12, 2)

    def test_pt_ka_below_threshold(self):
        pt = _compute_pt(12000.0, "KA", PARAMS)
        assert pt == 0.0

    def test_pt_ka_above_threshold(self):
        pt = _compute_pt(15000.0, "KA", PARAMS)
        assert pt == round(2400 / 12, 2)

    def test_pt_tn_nil(self):
        # Tamil Nadu: no PT
        pt = _compute_pt(50000.0, "TN", PARAMS)
        assert pt == 0.0

    def test_pt_unknown_state(self):
        # State not in config → 0
        pt = _compute_pt(50000.0, "XX", PARAMS)
        assert pt == 0.0


# ══════════════════════════════════════════════════════════════
# TDS
# ══════════════════════════════════════════════════════════════

class TestTDS:
    def _decl(self, regime="new", c80=0, c80d=0, hra=0, other_e=0, other_inc=0):
        return {"regime": regime, "investments_80c": c80, "investments_80d": c80d, "hra_exemption": hra, "other_exemptions": other_e, "other_income": other_inc}

    def test_new_regime_basic(self):
        # Annual gross 600,000; std deduction 50,000; taxable = 550,000
        # New regime: 0–3L=0%, 3–6L=5% → taxable in band = 550K-300K = 250K → tax = 12,500; cess 4% → 13,000
        result = _compute_tds_monthly(600_000, self._decl("new"), PARAMS, 4, 2024)
        assert result["annual_taxable_income"] == 550_000.0
        assert result["annual_tax"] == round(12_500 * 1.04, 2)

    def test_old_regime_with_80c(self):
        # Annual gross 800,000; std deduction 50,000; 80C 150,000 → taxable = 600,000
        # Old regime: 0–2.5L=0%, 2.5–5L=5%, 5–10L=20% → tax = 25000*5% + 100000*20% = 1250+20000 = 21250; cess → 22100
        result = _compute_tds_monthly(800_000, self._decl("old", c80=150_000), PARAMS, 4, 2024)
        assert result["annual_taxable_income"] == 600_000.0
        expected_tax = round((250_000 * 0.05 + 100_000 * 0.20) * 1.04, 2)
        assert result["annual_tax"] == expected_tax

    def test_old_vs_new_regime_different(self):
        """Key acceptance criterion: old and new regime produce different monthly TDS for the same gross."""
        gross = 1_000_000.0
        decl_old = self._decl("old", c80=150_000)
        decl_new = self._decl("new")
        old = _compute_tds_monthly(gross, decl_old, PARAMS, 4, 2024)
        new = _compute_tds_monthly(gross, decl_new, PARAMS, 4, 2024)
        assert old["monthly_tds"] != new["monthly_tds"]

    def test_tds_spreads_over_remaining_months(self):
        # April (month 1 of FY) → 12 remaining months
        result_april = _compute_tds_monthly(600_000, self._decl("new"), PARAMS, 4, 2024)
        assert result_april["remaining_months"] == 12

        # January (month 10 of FY) → 3 remaining months
        result_jan = _compute_tds_monthly(600_000, self._decl("new"), PARAMS, 1, 2025)
        assert result_jan["remaining_months"] == 3
        # Monthly TDS must be higher in Jan (same annual tax, fewer months)
        assert result_jan["monthly_tds"] > result_april["monthly_tds"]

    def test_mid_year_declaration_change_recomputes(self):
        """
        When a declaration changes mid-year, remaining months get recalculated.
        Employee earned 6L; already deducted 4 months of TDS; now changes regime.
        """
        gross = 700_000.0
        already_deducted = 5000.0
        decl_new = self._decl("new")
        result = _compute_tds_monthly(gross, decl_new, PARAMS, 8, 2024, already_deducted_tds=already_deducted)
        # Remaining months from August = 8
        assert result["remaining_months"] == 8
        assert result["already_deducted"] == already_deducted
        balance = result["annual_tax"] - already_deducted
        assert abs(result["monthly_tds"] - round(max(balance, 0) / 8, 2)) <= 0.01

    def test_tds_nil_for_low_income(self):
        # Annual gross 400,000; new regime; taxable = 350,000 → 50K in 5% band = 2500; cess → 2600
        result = _compute_tds_monthly(400_000, self._decl("new"), PARAMS, 4, 2024)
        assert result["annual_taxable_income"] == 350_000.0
        assert result["annual_tax"] == round(50_000 * 0.05 * 1.04, 2)  # 2,600
        # Gross 300,000 → taxable 250,000 → all in 0% band → nil tax
        result_nil = _compute_tds_monthly(300_000, self._decl("new"), PARAMS, 4, 2024)
        assert result_nil["annual_taxable_income"] == 250_000.0
        assert result_nil["annual_tax"] == 0.0
        assert result_nil["monthly_tds"] == 0.0


# ══════════════════════════════════════════════════════════════
# LOP (Loss of Pay)
# ══════════════════════════════════════════════════════════════

class TestLOP:
    def test_full_month_no_lop(self):
        result = _apply_lop(30000.0, paid_days=30, total_days=30)
        assert result == 30000.0

    def test_lop_2_days_in_30(self):
        result = _apply_lop(30000.0, paid_days=28, total_days=30)
        assert result == round(30000.0 * 28 / 30, 2)

    def test_lop_zero_paid_days(self):
        result = _apply_lop(30000.0, paid_days=0, total_days=31)
        assert result == 0.0

    def test_lop_single_day(self):
        # 1 LOP day in 31-day month
        result = _apply_lop(31000.0, paid_days=30, total_days=31)
        assert result == round(31000.0 * 30 / 31, 2)


# ══════════════════════════════════════════════════════════════
# Gratuity
# ══════════════════════════════════════════════════════════════

class TestGratuity:
    def test_gratuity_formula(self):
        # Basic = 20,000; 7 years → gratuity = 20000/26*15*7 = 80,769.23
        g = _compute_gratuity(20000.0, 7.0)
        assert g == round(20000.0 / 26 * 15 * 7, 2)

    def test_gratuity_not_eligible_below_5_years(self):
        g = _compute_gratuity(20000.0, 4.9)
        assert g == 0.0

    def test_gratuity_exactly_5_years(self):
        g = _compute_gratuity(20000.0, 5.0)
        assert g == round(20000.0 / 26 * 15 * 5, 2)

    def test_gratuity_zero_basic(self):
        g = _compute_gratuity(0.0, 10.0)
        assert g == 0.0


# ══════════════════════════════════════════════════════════════
# Remaining months helper
# ══════════════════════════════════════════════════════════════

class TestRemainingMonths:
    def test_april_start_of_fy(self):
        assert _remaining_months_in_fy(4, 2024) == 12

    def test_march_end_of_fy(self):
        assert _remaining_months_in_fy(3, 2025) == 1

    def test_october_mid_fy(self):
        assert _remaining_months_in_fy(10, 2024) == 6

    def test_january(self):
        assert _remaining_months_in_fy(1, 2025) == 3


# ══════════════════════════════════════════════════════════════
# Period helpers
# ══════════════════════════════════════════════════════════════

class TestPeriodHelpers:
    def test_parse_period(self):
        mm, yyyy = _parse_period("062025")
        assert mm == 6
        assert yyyy == 2025

    def test_period_days_31_day_month(self):
        assert _period_days(1, 2025) == 31

    def test_period_days_february_non_leap(self):
        assert _period_days(2, 2025) == 28

    def test_period_days_february_leap(self):
        assert _period_days(2, 2024) == 29


# ══════════════════════════════════════════════════════════════
# Tax slab engine
# ══════════════════════════════════════════════════════════════

class TestTaxSlabs:
    def test_new_regime_no_tax_below_3l(self):
        slabs = _default_tds_slabs("new")
        tax = _tax_from_slabs(250_000, slabs)
        assert tax == 0.0

    def test_new_regime_5pct_band(self):
        # 3L–6L at 5%; taxable = 500,000 → tax = 200,000 * 5% = 10,000
        slabs = _default_tds_slabs("new")
        tax = _tax_from_slabs(500_000, slabs)
        assert tax == 10_000.0

    def test_old_regime_20pct_band(self):
        # Old regime: 0–2.5L @0, 2.5–5L @5%, 5–10L @20%
        # Taxable 700,000: (250000*5% + 200000*20%) = 12500+40000 = 52500
        slabs = _default_tds_slabs("old")
        tax = _tax_from_slabs(700_000, slabs)
        assert tax == round(250_000 * 0.05 + 200_000 * 0.20, 2)

    def test_new_regime_top_rate(self):
        # >15L @30%; taxable 2,000,000
        slabs = _default_tds_slabs("new")
        tax = _tax_from_slabs(2_000_000, slabs)
        assert tax > 0
        # Expected: (300k*5% + 300k*10% + 300k*15% + 300k*20% + 500k*30%)
        expected = 300_000*0.05 + 300_000*0.10 + 300_000*0.15 + 300_000*0.20 + 500_000*0.30
        assert abs(tax - expected) < 1.0
