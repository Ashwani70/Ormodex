"""Stock valuation engine — pluggable FIFO and Weighted-Average strategies.

Pure functions over a chronological sequence of stock movements for a single
stock item. Each movement is a dict (or StockLedgerEntry-like) with at least:
    qty   : signed float (+ inward, - outward)
    rate  : cost per unit for inward moves (ignored for outward)
    entry_date : ISO date (used only for ordering/aging by the caller)

The engine computes the cost rate/value for outward movements and the closing
stock (qty + value). Strategies are interchangeable behind `value_movements`.

Design choices:
- FIFO keeps explicit cost layers (lots) so cost flows from oldest inward first
  and a layer/aging view is available.
- Weighted average maintains a running average cost, recomputed on each inward
  move; outward moves are valued at that running average.
- These functions never touch the DB, so they are trivially unit-testable.
"""
from dataclasses import dataclass, field
from typing import Callable

ROUND = 4  # internal rounding for rates/values to avoid float drift


@dataclass
class Layer:
    """A surviving FIFO cost lot."""
    qty: float
    rate: float
    entry_date: str | None = None
    source_doc_id: str | None = None


@dataclass
class ValuationResult:
    priced_movements: list[dict]      # input movements, outward ones now carrying rate/value
    layers: list[Layer]              # remaining cost layers (FIFO); [] for WA
    closing_qty: float
    closing_value: float
    running_avg_rate: float | None = None  # WA only
    errors: list[str] = field(default_factory=list)


def _r(x: float) -> float:
    return round(x, ROUND)


# ───────────────────────────── FIFO ─────────────────────────────

def value_fifo(movements: list[dict]) -> ValuationResult:
    """Consume oldest inward layers first for each outward movement."""
    layers: list[Layer] = []
    priced: list[dict] = []
    errors: list[str] = []

    for mv in movements:
        qty = float(mv.get("qty", 0))
        out = dict(mv)
        if qty > 0:
            # Inward: open a new layer at its own rate.
            rate = float(mv.get("rate") or 0.0)
            layers.append(Layer(qty=qty, rate=rate,
                                entry_date=mv.get("entry_date"),
                                source_doc_id=mv.get("source_doc_id")))
            out["rate"] = _r(rate)
            out["value"] = _r(qty * rate)
        elif qty < 0:
            # Outward: draw from oldest layers until satisfied.
            need = -qty
            consumed_value = 0.0
            consumed_qty = 0.0
            while need > 1e-9 and layers:
                layer = layers[0]
                take = min(layer.qty, need)
                consumed_value += take * layer.rate
                consumed_qty += take
                layer.qty -= take
                need -= take
                if layer.qty <= 1e-9:
                    layers.pop(0)
            if need > 1e-9:
                # Not enough stock to cost the full outward qty.
                errors.append(
                    f"FIFO: insufficient layers for outward {(-qty)} (short {need:.4f})"
                )
            cost_rate = (consumed_value / consumed_qty) if consumed_qty > 1e-9 else 0.0
            out["rate"] = _r(cost_rate)
            out["value"] = _r(-consumed_value)  # negative: value leaving stock
        else:
            out["rate"] = 0.0
            out["value"] = 0.0
        priced.append(out)

    closing_qty = _r(sum(l.qty for l in layers))
    closing_value = _r(sum(l.qty * l.rate for l in layers))
    return ValuationResult(priced, layers, closing_qty, closing_value, errors=errors)


# ──────────────────────── Weighted Average ────────────────────────

def value_weighted_avg(movements: list[dict]) -> ValuationResult:
    """Recompute the running average cost on each inward move; value outward at it."""
    running_qty = 0.0
    running_value = 0.0
    priced: list[dict] = []
    errors: list[str] = []

    for mv in movements:
        qty = float(mv.get("qty", 0))
        out = dict(mv)
        if qty > 0:
            rate = float(mv.get("rate") or 0.0)
            running_qty += qty
            running_value += qty * rate
            out["rate"] = _r(rate)
            out["value"] = _r(qty * rate)
        elif qty < 0:
            avg = (running_value / running_qty) if running_qty > 1e-9 else 0.0
            take = -qty
            if take > running_qty + 1e-9:
                errors.append(
                    f"WA: insufficient stock for outward {take} (have {running_qty:.4f})"
                )
            running_qty += qty            # qty is negative
            running_value += qty * avg    # remove at average cost
            if running_qty < 1e-9:
                running_qty = 0.0
                running_value = 0.0
            out["rate"] = _r(avg)
            out["value"] = _r(qty * avg)  # negative
        else:
            out["rate"] = 0.0
            out["value"] = 0.0
        priced.append(out)

    avg_rate = (running_value / running_qty) if running_qty > 1e-9 else 0.0
    return ValuationResult(
        priced, [], _r(running_qty), _r(running_value),
        running_avg_rate=_r(avg_rate), errors=errors,
    )


# ──────────────────────── Strategy dispatch ────────────────────────

_STRATEGIES: dict[str, Callable[[list[dict]], ValuationResult]] = {
    "FIFO": value_fifo,
    "WEIGHTED_AVG": value_weighted_avg,
}


def value_movements(movements: list[dict], method: str = "WEIGHTED_AVG") -> ValuationResult:
    """Value a chronological movement sequence using the named strategy.

    `movements` must already be sorted oldest-first by entry_date.
    """
    strategy = _STRATEGIES.get(method)
    if strategy is None:
        raise ValueError(f"Unknown valuation method: {method!r}")
    return strategy(movements)


def closing_value_as_of(movements: list[dict], method: str = "WEIGHTED_AVG") -> float:
    """Convenience: closing stock value after applying all movements."""
    return value_movements(movements, method).closing_value
