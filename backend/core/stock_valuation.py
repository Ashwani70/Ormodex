"""Stock valuation engine — pluggable FIFO, LIFO, Weighted-Average & Standard-Cost.

Pure functions over a chronological sequence of stock movements for a single
stock item. Each movement is a dict (or StockLedgerEntry-like) with at least:
    qty   : signed float (+ inward, - outward)
    rate  : cost per unit for inward moves (ignored for outward)
    entry_date : ISO date (used only for ordering/aging by the caller)

The engine computes the cost rate/value for outward movements and the closing
stock (qty + value). Strategies are interchangeable behind `value_movements`.

Design choices:
- FIFO/LIFO keep explicit cost layers (lots) so cost flows from the oldest
  (FIFO) or newest (LIFO) inward layer, and a layer/aging view is available.
- Weighted average maintains a running average cost, recomputed on each inward
  move; outward moves are valued at that running average.
- Standard cost values every outward move at a fixed per-unit standard rate
  (from the item master); the running inventory value is carried at standard so
  the ledger never drifts, and purchase-price variance is the caller's concern.
- These functions never touch the DB, so they are trivially unit-testable.

Method resolution (Item Override → Company Default) lives in `resolve_method`
so the DB layer has one place to decide which strategy an item uses.
"""
from dataclasses import dataclass, field
from typing import Callable

ROUND = 4  # internal rounding for rates/values to avoid float drift

# Canonical method identifiers used throughout the engine and ledger.
FIFO = "FIFO"
LIFO = "LIFO"
WEIGHTED_AVG = "WEIGHTED_AVG"
STANDARD_COST = "STANDARD_COST"

VALUATION_METHODS = (FIFO, LIFO, WEIGHTED_AVG, STANDARD_COST)
DEFAULT_METHOD = WEIGHTED_AVG

# Human-friendly / legacy spellings → canonical id. Keeps the UI, older data,
# and Tally-style labels ("Avg Cost", "Moving Average") all mapping cleanly.
_METHOD_ALIASES: dict[str, str] = {
    "FIFO": FIFO,
    "FIRST_IN_FIRST_OUT": FIFO,
    "LIFO": LIFO,
    "LAST_IN_FIRST_OUT": LIFO,
    "WEIGHTED_AVG": WEIGHTED_AVG,
    "WEIGHTED_AVERAGE": WEIGHTED_AVG,
    "MOVING_AVERAGE": WEIGHTED_AVG,
    "MOVING_AVG": WEIGHTED_AVG,
    "AVERAGE": WEIGHTED_AVG,
    "AVG": WEIGHTED_AVG,
    "STANDARD_COST": STANDARD_COST,
    "STANDARD": STANDARD_COST,
    "STD_COST": STANDARD_COST,
}


def canonical_method(method: str | None) -> str | None:
    """Normalise a method string to a canonical id, or None if unrecognised.

    Case/space/hyphen-insensitive. `None`/blank returns None so callers can fall
    back to the next level (item → company → engine default).
    """
    if not method:
        return None
    key = method.strip().upper().replace("-", "_").replace(" ", "_")
    return _METHOD_ALIASES.get(key)


def resolve_method(item_method: str | None = None,
                   company_default: str | None = None) -> str:
    """Resolve the effective valuation method: Item Override → Company Default.

    Falls back to the engine default (WEIGHTED_AVG) when neither is set/valid,
    so posting can never fail for want of a configured method.
    """
    return (
        canonical_method(item_method)
        or canonical_method(company_default)
        or DEFAULT_METHOD
    )


@dataclass
class Layer:
    """A surviving FIFO/LIFO cost lot."""
    qty: float
    rate: float
    entry_date: str | None = None
    source_doc_id: str | None = None


@dataclass
class ValuationResult:
    priced_movements: list[dict]      # input movements, outward ones now carrying rate/value
    layers: list[Layer]              # remaining cost layers (FIFO/LIFO); [] for WA/STD
    closing_qty: float
    closing_value: float
    running_avg_rate: float | None = None  # WA only
    method: str = DEFAULT_METHOD
    errors: list[str] = field(default_factory=list)


def _r(x: float) -> float:
    return round(x, ROUND)


# ─────────────────────── FIFO / LIFO (layered) ───────────────────────

def _value_layered(movements: list[dict], *, lifo: bool) -> ValuationResult:
    """Layer-consuming valuation. Outward draws oldest-first (FIFO) or
    newest-first (LIFO). One code path, one flag — the only difference is which
    end of the layer stack an outward move consumes from."""
    layers: list[Layer] = []
    priced: list[dict] = []
    errors: list[str] = []
    method = LIFO if lifo else FIFO

    for mv in movements:
        qty = float(mv.get("qty") or 0)
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
            # Outward: draw from the appropriate end until satisfied.
            need = -qty
            consumed_value = 0.0
            consumed_qty = 0.0
            while need > 1e-9 and layers:
                layer = layers[-1] if lifo else layers[0]
                take = min(layer.qty, need)
                consumed_value += take * layer.rate
                consumed_qty += take
                layer.qty -= take
                need -= take
                if layer.qty <= 1e-9:
                    layers.pop() if lifo else layers.pop(0)
            if need > 1e-9:
                # Not enough stock to cost the full outward qty.
                errors.append(
                    f"{method}: insufficient layers for outward {(-qty)} (short {need:.4f})"
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
    return ValuationResult(priced, layers, closing_qty, closing_value,
                           method=method, errors=errors)


def value_fifo(movements: list[dict]) -> ValuationResult:
    """Consume oldest inward layers first for each outward movement."""
    return _value_layered(movements, lifo=False)


def value_lifo(movements: list[dict]) -> ValuationResult:
    """Consume newest inward layers first for each outward movement.

    Note: LIFO layers are consumed newest-first, but the surviving `layers`
    list stays in chronological (insertion) order, so `layers[0]` is always the
    oldest surviving lot regardless of method — convenient for the aging view.
    """
    return _value_layered(movements, lifo=True)


# ──────────────────────── Weighted Average ────────────────────────

def value_weighted_avg(movements: list[dict]) -> ValuationResult:
    """Recompute the running average cost on each inward move; value outward at it."""
    running_qty = 0.0
    running_value = 0.0
    priced: list[dict] = []
    errors: list[str] = []

    for mv in movements:
        qty = float(mv.get("qty") or 0)
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
                    f"WEIGHTED_AVG: insufficient stock for outward {take} (have {running_qty:.4f})"
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
        running_avg_rate=_r(avg_rate), method=WEIGHTED_AVG, errors=errors,
    )


# ──────────────────────── Standard Cost ────────────────────────

def value_standard_cost(movements: list[dict], *, standard_cost: float = 0.0) -> ValuationResult:
    """Value every move at a fixed per-unit standard cost.

    Both inward and outward legs are carried at `standard_cost`, so on-hand
    value is always qty × standard and never drifts. The gap between an inward
    move's actual purchase rate and the standard (purchase-price variance) is
    surfaced per-move as ``variance`` for callers that post it to a variance
    account; it is deliberately kept OUT of inventory value.

    A zero/blank standard degrades to weighted-average (actual-cost) valuation
    so a misconfigured item is costed at what it actually cost, never at 0.
    """
    std = standard_cost or 0.0
    if std <= 1e-9:
        # No usable standard → value at actual cost. Reuse the WA engine so
        # outward moves draw the real running-average cost (they carry no rate
        # of their own), then relabel the result as STANDARD_COST.
        res = value_weighted_avg(movements)
        for m in res.priced_movements:
            m.setdefault("variance", 0.0)
        res.method = STANDARD_COST
        return res

    running_qty = 0.0
    priced: list[dict] = []
    errors: list[str] = []

    for mv in movements:
        qty = float(mv.get("qty") or 0)
        out = dict(mv)
        if qty > 0:
            actual = float(mv.get("rate") or 0.0)
            running_qty += qty
            out["rate"] = _r(std)
            out["value"] = _r(qty * std)
            # Purchase-price variance: (actual - standard) × qty. Positive =
            # bought above standard; kept OUT of inventory value on purpose.
            out["variance"] = _r((actual - std) * qty)
        elif qty < 0:
            take = -qty
            if take > running_qty + 1e-9:
                errors.append(
                    f"STANDARD_COST: insufficient stock for outward {take} (have {running_qty:.4f})"
                )
            running_qty += qty
            if running_qty < 1e-9:
                running_qty = 0.0
            out["rate"] = _r(std)
            out["value"] = _r(qty * std)   # negative
            out["variance"] = 0.0
        else:
            out["rate"] = 0.0
            out["value"] = 0.0
            out["variance"] = 0.0
        priced.append(out)

    return ValuationResult(
        priced, [], _r(running_qty), _r(running_qty * std),
        running_avg_rate=_r(std), method=STANDARD_COST, errors=errors,
    )


# ──────────────────────── Strategy dispatch ────────────────────────

_STRATEGIES: dict[str, Callable[..., ValuationResult]] = {
    FIFO: value_fifo,
    LIFO: value_lifo,
    WEIGHTED_AVG: value_weighted_avg,
    STANDARD_COST: value_standard_cost,
}


def value_movements(movements: list[dict], method: str = WEIGHTED_AVG,
                    *, standard_cost: float = 0.0) -> ValuationResult:
    """Value a chronological movement sequence using the named strategy.

    `movements` must already be sorted oldest-first by entry_date. `method` is
    canonicalised (aliases + case-insensitive); an unrecognised method raises,
    since silently guessing a valuation basis would be a data-integrity risk.
    `standard_cost` is only consulted by the STANDARD_COST strategy.
    """
    canon = canonical_method(method)
    strategy = _STRATEGIES.get(canon) if canon else None
    if strategy is None:
        raise ValueError(f"Unknown valuation method: {method!r}")
    if canon == STANDARD_COST:
        return strategy(movements, standard_cost=standard_cost)
    return strategy(movements)


def closing_value_as_of(movements: list[dict], method: str = WEIGHTED_AVG,
                        *, standard_cost: float = 0.0) -> float:
    """Convenience: closing stock value after applying all movements."""
    return value_movements(movements, method, standard_cost=standard_cost).closing_value
