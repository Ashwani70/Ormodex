"""Unit tests for the FIFO + Weighted-Average stock valuation engine.

Pure functions, no DB — run with plain pytest (no async plugin needed).

Mixed sequence used across both methods:
    In  10 @ 100
    In  10 @ 120
    Out 15
    In   5 @ 150
    Out  8

Hand-computed expectations:
  FIFO  : out#1 = 10*100 + 5*120 = 1600 ; out#2 = 5*120 + 3*150 = 1050
          closing = 2 @ 150 = 300
  WA    : avg after two ins = 110 ; out#1 = 15*110 = 1650 ; remaining 5 @ 110
          after in 5@150 -> qty 10, value 1300, avg 130 ; out#2 = 8*130 = 1040
          closing value = 260, closing qty = 2
"""
from core.stock_valuation import value_fifo, value_weighted_avg, value_movements


MIXED = [
    {"qty": 10, "rate": 100, "entry_date": "2026-01-01"},
    {"qty": 10, "rate": 120, "entry_date": "2026-01-02"},
    {"qty": -15, "entry_date": "2026-01-03"},
    {"qty": 5, "rate": 150, "entry_date": "2026-01-04"},
    {"qty": -8, "entry_date": "2026-01-05"},
]


def _outs(result):
    return [m for m in result.priced_movements if m["qty"] < 0]


# ───────────────────────────── FIFO ─────────────────────────────

def test_fifo_closing_qty_and_value():
    r = value_fifo(MIXED)
    assert r.closing_qty == 2
    assert r.closing_value == 300
    # One surviving layer: 2 @ 150
    assert len(r.layers) == 1
    assert r.layers[0].qty == 2
    assert r.layers[0].rate == 150
    assert not r.errors


def test_fifo_outward_values_consume_oldest_first():
    outs = _outs(value_fifo(MIXED))
    # value is negative (stock leaving); compare magnitudes
    assert abs(outs[0]["value"]) == 1600   # 10@100 + 5@120
    assert abs(outs[1]["value"]) == 1050   # 5@120 + 3@150


def test_fifo_blended_outward_rate():
    outs = _outs(value_fifo(MIXED))
    # out#1: 1600/15 ; out#2: 1050/8
    assert round(outs[0]["rate"], 4) == round(1600 / 15, 4)
    assert round(outs[1]["rate"], 4) == round(1050 / 8, 4)


# ──────────────────────── Weighted Average ────────────────────────

def test_wa_closing_qty_and_value():
    r = value_weighted_avg(MIXED)
    assert r.closing_qty == 2
    assert r.closing_value == 260
    assert r.running_avg_rate == 130
    assert not r.errors


def test_wa_outward_values_use_running_average():
    outs = _outs(value_weighted_avg(MIXED))
    assert abs(outs[0]["value"]) == 1650   # 15 @ 110
    assert abs(outs[1]["value"]) == 1040   # 8 @ 130


# ──────────────────────── Strategy dispatch & edges ────────────────────────

def test_dispatch_matches_direct_calls():
    assert value_movements(MIXED, "FIFO").closing_value == value_fifo(MIXED).closing_value
    assert value_movements(MIXED, "WEIGHTED_AVG").closing_value == value_weighted_avg(MIXED).closing_value


def test_unknown_method_raises():
    try:
        value_movements(MIXED, "LIFO")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown method")


def test_oversell_is_flagged_not_crashed():
    seq = [{"qty": 5, "rate": 100}, {"qty": -8}]
    for fn in (value_fifo, value_weighted_avg):
        r = fn(seq)
        assert r.errors, f"{fn.__name__} should flag overselling"


def test_full_consumption_leaves_zero():
    seq = [{"qty": 10, "rate": 50}, {"qty": -10}]
    rf = value_fifo(seq)
    rw = value_weighted_avg(seq)
    assert rf.closing_qty == 0 and rf.closing_value == 0
    assert rw.closing_qty == 0 and rw.closing_value == 0
