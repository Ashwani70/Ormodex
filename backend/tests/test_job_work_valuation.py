"""Unit tests for job-work challan line valuation (rate / GST / taxable value).

The full job-work flow tests are integration-style (need a live server); this
covers the pure enrichment helper added for the rate + GST feature.
"""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-jobwork-tests")

from routers.job_work import _enrich_item_valuation
from core.models import JobWorkChallan, JobWorkChallanItem


def test_catalog_item_fills_from_product():
    item = {"quantity": 5, "product_id": "p1"}
    _enrich_item_valuation(item, {"cost_price": 100, "hsn_code": "7308", "gst_rate": 18})
    assert item["rate"] == 100.0
    assert item["taxable_value"] == 500.0       # rate * qty
    assert item["hsn_code"] == "7308"
    assert item["gst_rate"] == 18.0


def test_explicit_rate_is_honoured_over_product_cost():
    item = {"quantity": 2, "rate": 50, "gst_rate": 12}
    _enrich_item_valuation(item, {"cost_price": 999, "gst_rate": 18})
    assert item["rate"] == 50.0
    assert item["taxable_value"] == 100.0
    assert item["gst_rate"] == 12              # line value kept, not overwritten


def test_custom_item_without_product_defaults_to_zero():
    item = {"quantity": 3, "is_custom": True}
    _enrich_item_valuation(item, None)
    assert item["rate"] == 0.0
    assert item["taxable_value"] == 0.0


def test_taxable_value_always_recomputed():
    # A stale/incoming taxable_value must be overwritten from rate * qty.
    item = {"quantity": 4, "rate": 10, "taxable_value": 99999}
    _enrich_item_valuation(item, None)
    assert item["taxable_value"] == 40.0


def test_model_accepts_rate_gst_and_gstin():
    m = JobWorkChallan(
        date="2026-06-20", job_worker_id="jw1",
        job_worker_gstin="27AAAAA0000A1Z5",
        items=[JobWorkChallanItem(product_name="X", quantity=1, rate=10, gst_rate=18, hsn_code="7308")],
    )
    assert m.job_worker_gstin == "27AAAAA0000A1Z5"
    assert m.items[0].rate == 10
    assert m.items[0].gst_rate == 18
    assert m.items[0].hsn_code == "7308"
