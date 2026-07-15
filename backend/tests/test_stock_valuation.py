"""Unit tests for the FIFO / LIFO / Weighted-Average / Standard-Cost engine.

Pure functions, no DB — run with plain pytest (no async plugin needed).

Mixed sequence used across FIFO/LIFO/WA:
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

The master-prompt worked examples (100@100, 200@110, 150@130, then Out 220) are
asserted verbatim in the FIFO/LIFO sections below.
"""
from core.stock_valuation import (
    value_fifo, value_lifo, value_weighted_avg, value_standard_cost,
    value_movements, canonical_method, resolve_method,
    FIFO, LIFO, WEIGHTED_AVG, STANDARD_COST, DEFAULT_METHOD,
)


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
        value_movements(MIXED, "NOPE")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown method")


def test_oversell_is_flagged_not_crashed():
    seq = [{"qty": 5, "rate": 100}, {"qty": -8}]
    for fn in (value_fifo, value_lifo, value_weighted_avg, value_standard_cost):
        r = fn(seq)
        assert r.errors, f"{fn.__name__} should flag overselling"


def test_full_consumption_leaves_zero():
    seq = [{"qty": 10, "rate": 50}, {"qty": -10}]
    for fn in (value_fifo, value_lifo, value_weighted_avg):
        r = fn(seq)
        assert r.closing_qty == 0 and r.closing_value == 0, fn.__name__


# ───────────────── Master-prompt worked examples: 100@100 / 200@110 / 150@130 ─────────────────

SPEC = [
    {"qty": 100, "rate": 100, "entry_date": "2026-01-01"},
    {"qty": 200, "rate": 110, "entry_date": "2026-01-02"},
    {"qty": 150, "rate": 130, "entry_date": "2026-01-03"},
    {"qty": -220, "entry_date": "2026-01-04"},   # sell 220
]


def test_fifo_spec_example():
    """FIFO sells 100@100 + 120@110 = 23200 COGS; leaves 80@110 + 150@130."""
    r = value_fifo(SPEC)
    cogs = abs(_outs(r)[0]["value"])
    assert cogs == 100 * 100 + 120 * 110       # 23200
    # Remaining layers: 80 @ 110, then 150 @ 130.
    assert [(l.qty, l.rate) for l in r.layers] == [(80, 110), (150, 130)]
    assert r.closing_qty == 230
    assert r.closing_value == 80 * 110 + 150 * 130   # 28300


def test_lifo_spec_example():
    """LIFO sells 150@130 + 70@110 = 27200 COGS; leaves 100@100 + 130@110."""
    r = value_lifo(SPEC)
    cogs = abs(_outs(r)[0]["value"])
    assert cogs == 150 * 130 + 70 * 110        # 27200
    # Surviving layers stay in chronological order: 100@100 (oldest), 130@110.
    assert [(l.qty, l.rate) for l in r.layers] == [(100, 100), (130, 110)]
    assert r.closing_qty == 230
    assert r.closing_value == 100 * 100 + 130 * 110  # 24300


def test_fifo_and_lifo_diverge_on_cogs():
    # Same inputs, different cost flow — the whole point of the two methods.
    assert abs(_outs(value_fifo(SPEC))[0]["value"]) == 23200
    assert abs(_outs(value_lifo(SPEC))[0]["value"]) == 27200


# ───────────────── Weighted-average 106.67 example from the spec ─────────────────

def test_wa_106_67_average():
    """100@100 then 200@110 → running avg 106.6667; Out 50 valued at it."""
    seq = [
        {"qty": 100, "rate": 100},
        {"qty": 200, "rate": 110},
        {"qty": -50},
    ]
    r = value_weighted_avg(seq)
    out = _outs(r)[0]
    assert round(out["rate"], 4) == round((100 * 100 + 200 * 110) / 300, 4)  # 106.6667
    assert round(out["rate"], 2) == 106.67
    assert abs(round(out["value"], 2)) == round(50 * (32000 / 300), 2)


def test_wa_recomputes_average_on_new_purchase():
    """After Out 50 (avg 106.67), a new In 100@120 shifts the running average."""
    seq = [
        {"qty": 100, "rate": 100},
        {"qty": 200, "rate": 110},
        {"qty": -50},
        {"qty": 100, "rate": 120},
    ]
    r = value_weighted_avg(seq)
    # Remaining before new buy: 250 @ 106.6667 = 26666.67; + 100@120 = 12000.
    # New avg = 38666.67 / 350 = 110.4762
    assert r.running_avg_rate is not None
    assert round(r.running_avg_rate, 4) == round(38666.6667 / 350, 4)


# ───────────────── Standard cost ─────────────────

def test_standard_cost_values_outward_at_standard():
    """Item standard 105; buys at 100 & 110; every sale costs at 105."""
    seq = [
        {"qty": 100, "rate": 100},
        {"qty": 50, "rate": 110},
        {"qty": -30},
    ]
    r = value_standard_cost(seq, standard_cost=105)
    out = _outs(r)[0]
    assert out["rate"] == 105
    assert abs(out["value"]) == 30 * 105          # 3150
    # Closing carried at standard: 120 on hand @ 105.
    assert r.closing_qty == 120
    assert r.closing_value == 120 * 105           # 12600


def test_standard_cost_purchase_price_variance():
    """Variance = (actual - standard) x qty, surfaced per inward move, not in value."""
    seq = [{"qty": 100, "rate": 100}, {"qty": 50, "rate": 110}]
    r = value_standard_cost(seq, standard_cost=105)
    ins = [m for m in r.priced_movements if m["qty"] > 0]
    assert ins[0]["variance"] == (100 - 105) * 100   # -500 (bought below std)
    assert ins[1]["variance"] == (110 - 105) * 50    # +250 (bought above std)


def test_standard_cost_zero_std_falls_back_to_actual():
    seq = [{"qty": 10, "rate": 100}, {"qty": -4}]
    r = value_standard_cost(seq, standard_cost=0)
    # No standard configured → degrade to actual cost, don't value stock at 0.
    assert abs(_outs(r)[0]["value"]) == 4 * 100
    assert r.closing_value == 6 * 100


# ───────────────── Method resolution & canonicalisation ─────────────────

def test_canonical_method_aliases():
    assert canonical_method("fifo") == FIFO
    assert canonical_method("Moving Average") == WEIGHTED_AVG
    assert canonical_method("weighted-avg") == WEIGHTED_AVG
    assert canonical_method("AVG") == WEIGHTED_AVG
    assert canonical_method("Standard Cost") == STANDARD_COST
    assert canonical_method("last_in_first_out") == LIFO
    assert canonical_method("garbage") is None
    assert canonical_method(None) is None
    assert canonical_method("") is None


def test_resolve_method_precedence():
    # Item override wins over company default.
    assert resolve_method("LIFO", "FIFO") == LIFO
    # No item override → company default.
    assert resolve_method(None, "FIFO") == FIFO
    assert resolve_method("", "standard cost") == STANDARD_COST
    # Neither set → engine default.
    assert resolve_method(None, None) == DEFAULT_METHOD == WEIGHTED_AVG
    # Invalid item method falls through to a valid company default.
    assert resolve_method("bogus", "LIFO") == LIFO


def test_dispatch_covers_all_four_methods():
    for m in (FIFO, LIFO, WEIGHTED_AVG):
        assert value_movements(MIXED, m).method == m
    # Standard cost needs its standard_cost kwarg threaded through dispatch.
    r = value_movements(
        [{"qty": 10, "rate": 100}, {"qty": -3}], STANDARD_COST, standard_cost=90
    )
    assert r.method == STANDARD_COST
    assert abs(_outs(r)[0]["value"]) == 3 * 90
