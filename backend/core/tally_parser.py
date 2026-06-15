"""Tally XML parser — Module K headline.

Parses Tally's XML export (the `<ENVELOPE>` / `TALLYMESSAGE` format) into our
own master + voucher shapes, using the Python stdlib (xml.etree) — no lxml
dependency. Tally exports are frequently Windows-1252 / ISO-8859-1 encoded and
contain its quirky `<AMOUNT>` sign convention (negative = debit for the party),
both handled here.

The functions are pure (string in → dicts out) so the dry-run preview and the
committed import run the SAME parse, making the preview trustworthy.

Tally primary groups → our account_type:
    Assets / Current Assets / Fixed Assets / Bank / Cash      → ASSET
    Liabilities / Current Liabilities / Loans / Duties&Taxes  → LIABILITY
    Capital Account / Reserves                                → EQUITY
    Sales Accounts / Direct Incomes / Indirect Incomes        → INCOME
    Purchase Accounts / Direct/Indirect Expenses              → EXPENSE
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as ET


# ── Tally group → account_type mapping (lower-cased keys) ──
_GROUP_TYPE_MAP = {
    "assets": "ASSET",
    "current assets": "ASSET",
    "fixed assets": "ASSET",
    "bank accounts": "ASSET",
    "bank account": "ASSET",
    "cash-in-hand": "ASSET",
    "cash in hand": "ASSET",
    "sundry debtors": "ASSET",
    "stock-in-hand": "ASSET",
    "deposits (asset)": "ASSET",
    "loans & advances (asset)": "ASSET",
    "liabilities": "LIABILITY",
    "current liabilities": "LIABILITY",
    "sundry creditors": "LIABILITY",
    "duties & taxes": "LIABILITY",
    "provisions": "LIABILITY",
    "loans (liability)": "LIABILITY",
    "secured loans": "LIABILITY",
    "unsecured loans": "LIABILITY",
    "capital account": "EQUITY",
    "reserves & surplus": "EQUITY",
    "sales accounts": "INCOME",
    "direct incomes": "INCOME",
    "indirect incomes": "INCOME",
    "purchase accounts": "EXPENSE",
    "direct expenses": "EXPENSE",
    "indirect expenses": "EXPENSE",
}

# Tally voucher type → our voucher_type
_VOUCHER_TYPE_MAP = {
    "sales": "SALES",
    "purchase": "PURCHASE",
    "receipt": "RECEIPT",
    "payment": "PAYMENT",
    "journal": "JOURNAL",
    "contra": "CONTRA",
    "debit note": "DEBIT_NOTE",
    "credit note": "CREDIT_NOTE",
}


def map_group_to_type(group_name: str, parent_chain: list[str] | None = None) -> str:
    """
    Resolve a Tally ledger's group to one of our account types. Tries the direct
    group name, then walks the parent chain (so a custom sub-group still maps via
    its primary ancestor). Defaults to ASSET if nothing matches (caller flags it
    for manual mapping in the preview).
    """
    candidates = [group_name] + list(parent_chain or [])
    for name in candidates:
        if not name:
            continue
        key = name.strip().lower()
        if key in _GROUP_TYPE_MAP:
            return _GROUP_TYPE_MAP[key]
    return "ASSET"   # unmapped → flagged in preview


def map_voucher_type(tally_vtype: str) -> str:
    return _VOUCHER_TYPE_MAP.get((tally_vtype or "").strip().lower(), "JOURNAL")


def _decode(xml_bytes: bytes | str) -> str:
    """Tally exports are often Windows-1252. Decode robustly."""
    if isinstance(xml_bytes, str):
        return xml_bytes
    for enc in ("utf-8", "cp1252", "iso-8859-1"):
        try:
            return xml_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return xml_bytes.decode("utf-8", errors="replace")


def _clean(text: str | None) -> str:
    return (text or "").strip()


def _to_float(text: str | None) -> float:
    """Tally amounts may be like '-1,234.50' or '1234.50 Dr'. Strip non-numeric."""
    if not text:
        return 0.0
    t = text.strip().replace(",", "")
    t = re.sub(r"[^0-9.\-]", "", t)
    if t in ("", "-", ".", "-."):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def _findtext(el, tag: str) -> str:
    child = el.find(tag)
    return _clean(child.text) if child is not None else ""


def parse_tally_xml(xml_bytes: bytes | str) -> dict:
    """
    Parse a Tally XML export into masters + vouchers.

    Returns:
      {
        "ledgers":     [{name, parent, account_type, opening_balance}],
        "groups":      [{name, parent}],
        "stock_items": [{name, unit, opening_qty, opening_rate}],
        "units":       [{name}],
        "vouchers":    [{date, voucher_type, number, party, narration,
                         lines: [{ledger, amount, is_debit}], total}],
        "errors":      [str],   # non-fatal per-element parse issues
      }
    """
    text = _decode(xml_bytes)
    result = {"ledgers": [], "groups": [], "stock_items": [], "units": [], "vouchers": [], "errors": []}

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        result["errors"].append(f"XML parse error: {e}")
        return result

    # Tally wraps masters/vouchers in TALLYMESSAGE elements (often namespaced/UDF).
    for msg in root.iter():
        tag = msg.tag.split("}")[-1].upper()
        if tag != "TALLYMESSAGE":
            continue
        for el in list(msg):
            etag = el.tag.split("}")[-1].upper()
            try:
                if etag == "GROUP":
                    result["groups"].append({
                        "name": el.get("NAME") or _findtext(el, "NAME"),
                        "parent": _findtext(el, "PARENT"),
                    })
                elif etag == "LEDGER":
                    name = el.get("NAME") or _findtext(el, "NAME")
                    parent = _findtext(el, "PARENT")
                    result["ledgers"].append({
                        "name": name,
                        "parent": parent,
                        "account_type": map_group_to_type(parent),
                        "opening_balance": _to_float(_findtext(el, "OPENINGBALANCE")),
                    })
                elif etag == "STOCKITEM":
                    result["stock_items"].append({
                        "name": el.get("NAME") or _findtext(el, "NAME"),
                        "unit": _findtext(el, "BASEUNITS"),
                        "opening_qty": _to_float(_findtext(el, "OPENINGBALANCE")),
                        "opening_rate": _to_float(_findtext(el, "OPENINGRATE")),
                    })
                elif etag == "UNIT":
                    result["units"].append({"name": el.get("NAME") or _findtext(el, "NAME")})
                elif etag == "VOUCHER":
                    result["vouchers"].append(_parse_voucher(el))
            except Exception as ex:  # never let one bad element abort the import
                result["errors"].append(f"{etag} parse error: {ex}")

    return result


def _parse_voucher(el) -> dict:
    vtype_raw = el.get("VCHTYPE") or _findtext(el, "VOUCHERTYPENAME")
    lines = []
    # Ledger entries can appear under several tag names across Tally versions.
    for le in el.iter():
        letag = le.tag.split("}")[-1].upper()
        if letag in ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST"):
            ledger = _findtext(le, "LEDGERNAME")
            amount = _to_float(_findtext(le, "AMOUNT"))
            # Tally convention: negative AMOUNT = debit to that ledger
            is_debit = amount < 0
            lines.append({"ledger": ledger, "amount": round(abs(amount), 2), "is_debit": is_debit})

    total = round(sum(l["amount"] for l in lines if l["is_debit"]), 2)
    return {
        "date": _findtext(el, "DATE"),
        "voucher_type": map_voucher_type(vtype_raw),
        "tally_voucher_type": vtype_raw,
        "number": _findtext(el, "VOUCHERNUMBER"),
        "party": _findtext(el, "PARTYLEDGERNAME") or _findtext(el, "PARTYNAME"),
        "narration": _findtext(el, "NARRATION"),
        "lines": lines,
        "total": total,
    }


def build_preview(parsed: dict, existing_ledger_names: set[str]) -> dict:
    """
    Build a dry-run preview: counts, what's new vs duplicate, unmapped ledgers,
    and validation flags — WITHOUT committing anything.
    """
    new_ledgers, dup_ledgers, unmapped = [], [], []
    seen = set()
    for lg in parsed["ledgers"]:
        nm = lg["name"]
        if nm in existing_ledger_names:
            dup_ledgers.append(nm)
        elif nm in seen:
            dup_ledgers.append(nm)   # duplicate within the file
        else:
            new_ledgers.append(nm)
        seen.add(nm)
        # account_type defaulted to ASSET only because no group matched → flag it
        if lg["parent"] and lg["parent"].strip().lower() not in _GROUP_TYPE_MAP and lg["account_type"] == "ASSET":
            unmapped.append({"ledger": nm, "group": lg["parent"]})

    unbalanced = []
    for v in parsed["vouchers"]:
        dr = round(sum(l["amount"] for l in v["lines"] if l["is_debit"]), 2)
        cr = round(sum(l["amount"] for l in v["lines"] if not l["is_debit"]), 2)
        if abs(dr - cr) > 0.01:
            unbalanced.append({"number": v["number"], "debit": dr, "credit": cr})

    return {
        "summary": {
            "groups": len(parsed["groups"]),
            "ledgers": len(parsed["ledgers"]),
            "stock_items": len(parsed["stock_items"]),
            "units": len(parsed["units"]),
            "vouchers": len(parsed["vouchers"]),
        },
        "ledgers_new": len(new_ledgers),
        "ledgers_duplicate": len(dup_ledgers),
        "unmapped_ledgers": unmapped,
        "unbalanced_vouchers": unbalanced,
        "parse_errors": parsed["errors"],
        "ready_to_commit": len(unbalanced) == 0 and len(parsed["errors"]) == 0,
    }
