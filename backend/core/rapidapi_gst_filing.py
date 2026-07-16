"""
GST return filing status lookup via the RapidAPI GST Return Filing Data API.

Endpoint: GET /v1/gst-returns/{gstin}/{financial_year}
Host: gst-return-filing-data.p.rapidapi.com

Provides filing history (GSTR-1, GSTR-3B, GSTR-2X, GSTR-1A, etc.)
for a given GSTIN in a specific financial year.
"""
import os
import httpx
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24


# ── Error hierarchy ───────────────────────────────────────────────────
class GstFilingProviderError(Exception):
    """Base class for GST filing provider failures."""
    user_message = "GST filing service error."


class GstFilingNotConfigured(GstFilingProviderError):
    user_message = "GST filing lookup is not configured — provider credentials missing."


class GstFilingAuthError(GstFilingProviderError):
    user_message = "GST filing service authentication failed — check credentials."


class GstFilingUnavailable(GstFilingProviderError):
    """Network / 5xx / timeout — transient, worth retrying later."""
    user_message = "GST filing service unavailable. Please try again shortly."


class GstFilingNotFound(GstFilingProviderError):
    user_message = "No GST filing data found for this GSTIN / financial year."


# ── Configuration check ──────────────────────────────────────────────
def is_configured() -> bool:
    """True when the RapidAPI key is set (filing host has a usable default)."""
    key = os.environ.get("RAPIDAPI_KEY", "")
    return bool(key and key != "your_rapidapi_key_here")


# ── Core lookup ──────────────────────────────────────────────────────
async def fetch_filing_status(gstin: str, financial_year: str) -> dict:
    """
    Fetch GST return filing history for a GSTIN and financial year.

    Args:
        gstin: 15-character GST identification number (e.g. '24AABCA2804L1Z0')
        financial_year: Format 'YYYY-YY' (e.g. '2024-25')

    Returns:
        dict with keys:
          - gstin: str
          - financial_year: str
          - filings: list of normalized filing records
          - summary: dict with return-type counts
          - source: 'rapidapi_filing'
    """
    if not is_configured():
        raise GstFilingNotConfigured()

    gstin = gstin.strip().upper()
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    api_host = os.environ.get("RAPIDAPI_FILING_HOST",
                              "gst-return-filing-data.p.rapidapi.com")

    url = f"https://{api_host}/v1/gst-returns/{gstin}/{financial_year}"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": api_host,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code in (401, 403):
                raise GstFilingAuthError()
            if resp.status_code == 404:
                raise GstFilingNotFound()
            if resp.status_code >= 500:
                raise GstFilingUnavailable()
            resp.raise_for_status()
            res_data = resp.json()
    except (httpx.TimeoutException, httpx.TransportError) as e:
        logger.warning("RapidAPI filing lookup network error: %s",
                       type(e).__name__)
        raise GstFilingUnavailable() from e
    except GstFilingProviderError:
        raise
    except Exception as e:
        logger.exception("Unexpected error during RapidAPI filing lookup")
        raise GstFilingUnavailable() from e

    # The API returns {"data": [...]} on success
    raw_filings = []
    if isinstance(res_data, dict):
        raw_filings = res_data.get("data", [])
    elif isinstance(res_data, list):
        raw_filings = res_data

    if not raw_filings:
        raise GstFilingNotFound()

    # Normalize each filing record
    filings = _normalize_filings(raw_filings)

    # Build summary by return type
    summary = {}
    for f in filings:
        rt = f["return_type"]
        summary.setdefault(rt, {"filed": 0, "total": 0})
        summary[rt]["total"] += 1
        if f["status"] == "Filed":
            summary[rt]["filed"] += 1

    return {
        "gstin": gstin,
        "financial_year": financial_year,
        "filings": filings,
        "total_filings": len(filings),
        "summary": summary,
        "source": "rapidapi_filing",
    }


def _normalize_filings(raw: list) -> list:
    """Normalize raw API filing records into a consistent shape."""
    filings = []
    for item in raw:
        # Normalize: providers return "GSTR-1", "GSTR-3B" etc.; strip hyphens
        # so compliance lookups using "GSTR1" / "GSTR3B" match correctly.
        raw_rt = str(item.get("return_type") or "").upper().replace("-", "").replace(" ", "")
        filings.append({
            "return_type": raw_rt,
            "return_period": item.get("return_period", ""),
            "return_period_formatted": item.get("return_period_formatted", ""),
            "status": item.get("status", "Not Filed"),
            "date_of_filing": item.get("date_of_filing", ""),
            "mode_of_filing": item.get("mode_of_filing", ""),
            "acknowledgement_number": item.get("acknowledgement_number", ""),
            "fiscal_year": item.get("fiscal_year", ""),
            "month": item.get("month"),
            "year": item.get("year"),
            "valid": item.get("valid", False),
        })
    # Sort by year desc, month desc, then return_type
    filings.sort(key=lambda f: (
        -(f.get("year") or 0),
        -(f.get("month") or 0),
        f["return_type"],
    ))
    return filings


# ── Caching layer ────────────────────────────────────────────────────
async def fetch_with_cache(db, gstin: str, financial_year: str,
                           force_refresh: bool = False) -> dict:
    """
    Fetch filing status with MongoDB caching.
    Cache key: gstin + financial_year.
    TTL: 24 hours (configurable via CACHE_TTL_HOURS).
    """
    cache_key = f"{gstin.upper()}_{financial_year}"

    if not force_refresh:
        cached = await db.gst_filing_cache.find_one(
            {"cache_key": cache_key}, {"_id": 0}
        )
        if cached:
            cached_at = cached.get("cached_at", "")
            if cached_at:
                try:
                    ts = datetime.fromisoformat(cached_at)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - ts < timedelta(
                            hours=CACHE_TTL_HOURS):
                        cached["from_cache"] = True
                        return cached
                except (ValueError, TypeError):
                    pass  # stale / malformed — fetch fresh

    # Fetch fresh data
    result = await fetch_filing_status(gstin, financial_year)
    result["cache_key"] = cache_key
    result["cached_at"] = datetime.now(timezone.utc).isoformat()
    result["from_cache"] = False

    # Upsert into cache
    await db.gst_filing_cache.update_one(
        {"cache_key": cache_key},
        {"$set": result},
        upsert=True,
    )

    return result


async def check_vendor_filing_compliance(
    db, vendor_gstins: list, return_period: str, financial_year: str
) -> list:
    """
    Check filing compliance for a list of vendor GSTINs.

    Args:
        vendor_gstins: list of dicts with 'gstin' and 'vendor_name'
        return_period: MMYYYY format (e.g. '052024')
        financial_year: YYYY-YY format (e.g. '2024-25')

    Returns:
        list of compliance dicts per vendor
    """
    results = []
    for v in vendor_gstins:
        gstin = v.get("gstin", "").strip().upper()
        vendor_name = v.get("vendor_name", "Unknown")

        if not gstin or len(gstin) != 15:
            results.append({
                "gstin": gstin,
                "vendor_name": vendor_name,
                "gstr1_filed": False,
                "gstr1_date": "",
                "gstr3b_filed": False,
                "gstr3b_date": "",
                "itc_risk": "HIGH",
                "error": "Invalid GSTIN",
            })
            continue

        try:
            data = await fetch_with_cache(db, gstin, financial_year)
            filings = data.get("filings", [])

            # Check GSTR-1 for the specific return period
            gstr1 = next(
                (f for f in filings
                 if f["return_type"] == "GSTR1"
                 and f["return_period"] == return_period),
                None,
            )
            gstr3b = next(
                (f for f in filings
                 if f["return_type"] == "GSTR3B"
                 and f["return_period"] == return_period),
                None,
            )

            gstr1_filed = gstr1 is not None and gstr1.get("status") == "Filed"
            gstr3b_filed = (gstr3b is not None
                           and gstr3b.get("status") == "Filed")

            # Determine ITC risk
            if not gstr1_filed:
                itc_risk = "HIGH"
            elif not gstr3b_filed:
                itc_risk = "MEDIUM"
            else:
                itc_risk = "LOW"

            results.append({
                "gstin": gstin,
                "vendor_name": vendor_name,
                "gstr1_filed": gstr1_filed,
                "gstr1_date": gstr1.get("date_of_filing", "") if gstr1 else "",
                "gstr1_arn": (gstr1.get("acknowledgement_number", "")
                              if gstr1 else ""),
                "gstr3b_filed": gstr3b_filed,
                "gstr3b_date": (gstr3b.get("date_of_filing", "")
                                if gstr3b else ""),
                "gstr3b_arn": (gstr3b.get("acknowledgement_number", "")
                               if gstr3b else ""),
                "itc_risk": itc_risk,
                "total_filings": len(filings),
            })
        except GstFilingNotFound:
            results.append({
                "gstin": gstin,
                "vendor_name": vendor_name,
                "gstr1_filed": False,
                "gstr1_date": "",
                "gstr3b_filed": False,
                "gstr3b_date": "",
                "itc_risk": "HIGH",
                "error": "No filing data found",
            })
        except GstFilingProviderError as e:
            results.append({
                "gstin": gstin,
                "vendor_name": vendor_name,
                "gstr1_filed": False,
                "gstr1_date": "",
                "gstr3b_filed": False,
                "gstr3b_date": "",
                "itc_risk": "UNKNOWN",
                "error": e.user_message,
            })

    return results
