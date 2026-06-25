"""Server-side enforcement of batch / serial / expiry tracking rules.

The linked ``stock_item`` is the source of truth: if it sets ``track_batch``,
``track_serial`` or ``track_expiry``, then every line that moves that item
through the stock ledger must carry the corresponding value. This is enforced
here — in the request handlers — so the rule holds regardless of the UI, for
API clients and bulk imports alike.

Flags are resolved in a single batched pass (core.product_stock_bridge), so
validating a multi-line document is O(distinct items), not O(lines).

Field expectations on a line:
  - track_batch  → ``batch_id``
  - track_serial → ``serial_id``
  - track_expiry → ``expiry_date``

Backward compatible: a line for an untracked item (the common case, and every
legacy ``stock_item_id``-only line whose item sets no flags) is accepted as-is.
"""
from typing import Optional

from fastapi import HTTPException

from core.product_stock_bridge import line_tracking_flags

# (flag on the stock_item) → (field the line must provide, human label)
_REQUIRED_FIELDS = (
    ("track_batch", "batch_id", "Batch number"),
    ("track_serial", "serial_id", "Serial number"),
    ("track_expiry", "expiry_date", "Expiry date"),
)


def _line_label(line: dict, index: int) -> str:
    return (
        line.get("product_name")
        or line.get("item_name")
        or line.get("product_id")
        or line.get("stock_item_id")
        or f"line {index + 1}"
    )


def _missing(line: dict, field: str) -> bool:
    val = line.get(field)
    return val is None or (isinstance(val, str) and not val.strip())


async def validate_tracking_fields(lines: list[dict], flags: Optional[dict[int, dict]] = None) -> None:
    """Raise HTTP 400 if any line omits a value its stock_item requires.

    ``flags`` may be supplied by callers that already resolved them (to avoid a
    second pass); otherwise they are resolved here. ``lines`` are dicts that have
    already had product_id → stock_item_id resolution applied where relevant.
    """
    if not lines:
        return
    if flags is None:
        flags = await line_tracking_flags(lines)

    for i, line in enumerate(lines):
        line_flags = flags.get(i, {})
        for flag, field, label in _REQUIRED_FIELDS:
            if line_flags.get(flag) and _missing(line, field):
                raise HTTPException(
                    status_code=400,
                    detail=f"{label} is required for '{_line_label(line, i)}'.",
                )
