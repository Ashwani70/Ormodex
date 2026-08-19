import pytest
import io
from fastapi import HTTPException
import core
import core.db
import core.utils as utils
import core.stock_ledger as sl
import core.po_numbering
from core.purchase_models import PurchaseOrderV2, POLine
from routers.purchase_v2 import create_order, update_order, order_pdf
from tests.test_grn_v2 import _DB, USER


def get_pdf_page_count_and_text(pdf_bytes: bytes) -> tuple[int, str | None]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return page_count, text
    except ImportError:
        return 1, None


def _setup():
    from typing import Any
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    sl.db = db
    core.po_numbering.db = db
    import routers.purchase_v2
    routers.purchase_v2.db = db
    from core import product_stock_bridge
    product_stock_bridge.db = db

    async def mock_crud_create(collection: str, data: dict, user: dict | None = None) -> dict:
        if not data.get("id"):
            data["id"] = utils.new_id()
        doc = dict(data)
        doc.setdefault("created_at", utils.now_iso())
        doc.setdefault("updated_at", utils.now_iso())
        await db[collection].insert_one(doc)
        return doc

    async def mock_crud_get(collection: str, doc_id: str, label: str = "Record") -> dict:
        doc = await db[collection].find_one({"id": doc_id})
        if not doc:
            raise HTTPException(404, f"{label} not found")
        return doc

    async def mock_crud_update(collection: str, doc_id: str, updates: dict, user: dict | None = None, label: str = "Record") -> dict:
        updates = dict(updates)
        updates["updated_at"] = utils.now_iso()
        await db[collection].update_one({"id": doc_id}, {"$set": updates})
        return await mock_crud_get(collection, doc_id, label=label)

    routers.purchase_v2.crud_create = mock_crud_create
    routers.purchase_v2.crud_get = mock_crud_get
    routers.purchase_v2.crud_update = mock_crud_update
    utils.crud_get = mock_crud_get
    utils.crud_create = mock_crud_create
    utils.crud_update = mock_crud_update
    product_stock_bridge.crud_get = mock_crud_get

    return db


@pytest.mark.asyncio
async def test_po_remarks_and_line_description_end_to_end():
    """Verify PO remarks, line item descriptions (yellow zinc plating / te zinc plating), single page layout, and edit persistence."""
    db = _setup()

    vendor_id = "v_test_1"
    product_id_1 = "p_test_1"
    product_id_2 = "p_test_2"
    await db["vendors"].insert_one({"id": vendor_id, "company": "Acme Steel Corp", "state": "Maharashtra"})
    await db["products"].insert_one({"id": product_id_1, "name": "HANDLE 10MM", "hsn_sac": "7308"})
    await db["products"].insert_one({"id": product_id_2, "name": "U BASE JACK", "hsn_sac": "9998"})
    await db["stock_items"].insert_one({"id": "i1", "product_id": product_id_1, "name": "HANDLE 10MM"})
    await db["stock_items"].insert_one({"id": "i2", "product_id": product_id_2, "name": "U BASE JACK"})

    po_payload = PurchaseOrderV2(
        vendor_id=vendor_id,
        notes="45 DAYS CREDIT (F.O.R)",
        remarks="45 DAYS CREDIT (F.O.R)",
        lines=[
            POLine(
                stock_item_id="i1",
                product_id=product_id_1,
                product_name="HANDLE 10MM",
                description="yellow zinc plating",
                hsn_code="7308",
                unit="Nos",
                qty=2280.0,
                rate=13.50,
                gst_rate=18.0,
            ),
            POLine(
                stock_item_id="i2",
                product_id=product_id_2,
                product_name="U BASE JACK",
                description="te zinc plating",
                hsn_code="9998",
                unit="Nos",
                qty=5250.0,
                rate=11.50,
                gst_rate=18.0,
            )
        ]
    )

    created = await create_order(po_payload, user=USER)
    po_id = created["id"]

    # 1. Verify DB persistence and line descriptions
    assert created.get("notes") == "45 DAYS CREDIT (F.O.R)"
    assert created.get("remarks") == "45 DAYS CREDIT (F.O.R)"
    assert len(created.get("lines", [])) == 2
    assert created["lines"][0]["description"] == "yellow zinc plating"
    assert created["lines"][1]["description"] == "te zinc plating"

    # 2. Verify PDF generation via API router
    pdf_resp = await order_pdf(po_id, user=USER)
    assert pdf_resp.status_code == 200
    pdf_bytes = pdf_resp.body
    assert isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 0

    page_count, pdf_text = get_pdf_page_count_and_text(pdf_bytes)
    assert page_count == 1, f"Expected 1 page for 2-item PO, got {page_count} pages"

    if pdf_text is not None:
        assert "REMARKS" in pdf_text
        assert "45 DAYS CREDIT (F.O.R)" in pdf_text
        assert "HANDLE 10MM" in pdf_text
        assert "yellow zinc plating" in pdf_text
        assert "U BASE JACK" in pdf_text
        assert "te zinc plating" in pdf_text

    # 3. Verify Edit PO updates descriptions and remarks
    edit_payload = PurchaseOrderV2(
        vendor_id=vendor_id,
        notes="60 DAYS CREDIT (EX-WORKS)",
        remarks="60 DAYS CREDIT (EX-WORKS)",
        lines=[
            POLine(
                stock_item_id="i1",
                product_id=product_id_1,
                product_name="HANDLE 10MM",
                description="yellow zinc plating premium finish",
                hsn_code="7308",
                unit="Nos",
                qty=2280.0,
                rate=13.50,
                gst_rate=18.0,
            ),
            POLine(
                stock_item_id="i2",
                product_id=product_id_2,
                product_name="U BASE JACK",
                description="te zinc plating premium finish",
                hsn_code="9998",
                unit="Nos",
                qty=5250.0,
                rate=11.50,
                gst_rate=18.0,
            )
        ]
    )

    updated = await update_order(po_id, edit_payload, user=USER)
    assert updated.get("notes") == "60 DAYS CREDIT (EX-WORKS)"
    assert updated.get("remarks") == "60 DAYS CREDIT (EX-WORKS)"
    assert len(updated["lines"]) == 2
    assert updated["lines"][0]["description"] == "yellow zinc plating premium finish"
    assert updated["lines"][1]["description"] == "te zinc plating premium finish"

    updated_pdf_resp = await order_pdf(po_id, user=USER)
    updated_pdf_bytes = updated_pdf_resp.body
    assert isinstance(updated_pdf_bytes, bytes) and len(updated_pdf_bytes) > 0

    updated_page_count, updated_pdf_text = get_pdf_page_count_and_text(updated_pdf_bytes)
    assert updated_page_count == 1, f"Expected 1 page after edit, got {updated_page_count}"

    if updated_pdf_text is not None:
        assert "60 DAYS CREDIT (EX-WORKS)" in updated_pdf_text
        assert "yellow zinc plating premium finish" in updated_pdf_text
        assert "te zinc plating premium finish" in updated_pdf_text
