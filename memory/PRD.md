# GRAVITY ENGINEERING WORKS — ERP / CRM / Inventory

## Original Problem Statement
Build a professional Inventory Management and CRM Application for a scaffolding manufacturing company (Gravity Engineering Works). The app must cover Authentication, Inventory, Purchase, Sales, CRM, Dispatch, Warehouse, GST Invoicing, Reports & Analytics, and Barcode/QR support. Theme: Black + White + Yellow industrial.

## Stack
- Frontend: React (CRA + craco) + Tailwind + shadcn/ui + Recharts
- Backend: FastAPI + Motor (MongoDB) + reportlab (PDF) + Emergent object-storage (image uploads)
- Auth: JWT (httpOnly cookies + Bearer fallback)
- Theme: Industrial Black/White/**Yellow** (Chivo + IBM Plex Sans)
- Comms: WhatsApp deep links (`wa.me`) + `mailto:` (no third-party APIs)

## Personas
- **Admin** — full access including user management and hard-deletes.
- **Employee / Operator** — read/write CRUD on all business modules; cannot hard-delete records or manage users.

## Architecture
```
backend/
├── server.py              # ~75 lines — entry point, mounts routers
├── core/
│   ├── db.py              # MongoDB client + close
│   ├── auth_utils.py      # JWT helpers + get_current_user / require_admin deps
│   ├── models.py          # All Pydantic models (incl. multi-currency fields)
│   ├── utils.py           # ID, timestamp, doc-numbering, calc_totals, generic CRUD
│   ├── storage.py         # Emergent object-storage client
│   ├── pdf.py             # reportlab document builder (currency-aware)
│   └── seed.py            # Admin + demo data seeding
└── routers/
    ├── auth.py
    ├── users.py
    ├── inventory.py       # products, warehouses, stock log, file uploads
    ├── purchase.py        # suppliers, purchase orders
    ├── sales.py           # customers, leads, quotations, sales orders, invoices, dispatches, PDF
    └── reports.py         # dashboard summary + reports
```

## Modules Implemented
| Module | Status | Notes |
|---|---|---|
| Authentication | ✅ | JWT + bcrypt + cookies + Bearer fallback |
| Inventory — Products | ✅ | CRUD + SKU uniqueness + **uploaded image (object storage)** + low-stock + GST + HSN + QR |
| Inventory — Warehouses | ✅ | CRUD |
| Inventory — Stock Log | ✅ | Append-only ledger |
| Purchase — Suppliers | ✅ | CRUD |
| Purchase — Purchase Orders | ✅ | Auto-numbered, /receive adds stock |
| CRM — Customers | ✅ | CRUD + CSV export |
| CRM — Leads | ✅ | Kanban + WhatsApp/Email/Call |
| Sales — Quotations | ✅ | Auto-numbered + **multi-currency** + **PDF download** |
| Sales — Sales Orders | ✅ | Stock-deducting confirm + **multi-currency** + **PDF download** |
| Sales — GST Invoices | ✅ | Payment tracking + **multi-currency** + **PDF download** |
| Logistics — Dispatch Challans | ✅ | Vehicle/driver + **PDF download** |
| Export — Proforma Invoices | ✅ | Auto-numbered PI-YY-NNNNN, multi-currency, Incoterms, ports, bank details, freight clauses, **export-grade PDF with amount-in-words** |
| Reports & Analytics | ✅ | Pie + bar charts, CSV exports |
| Admin Dashboard | ✅ | KPIs, sales trend, lead funnel, low-stock, quick links |
| Users (admin only) | ✅ | Manage operators |

## New in iteration 3
- **Proforma Invoice (PI) module** for export buyers — modeled after a real export PI sample (FECOCIVIL S.A. Portugal). Includes auto-numbered PI-YY-NNNNN, full buyer/consignee block, exporter + IEC, bank details (SWIFT/IBAN/A/C), per-currency Incoterms (FOB/CIF/CFR/EXW/CIP/DAP/DDP), country of origin, port of loading & discharge, final destination, payment & delivery terms, packing & freight clauses, line items with `container_spec` + `weight_per_unit` + `quantity` + `unit_price`. Server computes total quantity, total net weight (kg), total amount.
- **Export-grade PDF** built with reportlab: black header bar with company name + yellow PI badge, two-column buyer/logistics block, currency-aware line item table, yellow TOTAL row, amount-in-words (Dollars/Euros/Pounds/Dirhams/Rupees with decimals → Cents/Pence/Fils/Paise), bank+terms two-column footer, dual signature block.
- New helper `core/words.py` — international number-to-words converter (handles up to trillions, per-currency major/minor units).

## New in iteration 2
- **Object-storage product images** — POST `/api/uploads/product-image` (multipart, ≤6MB, jpg/png/webp/gif). Served via GET `/api/files/{path}` (auth required, blob fetch on frontend).
- **PDF endpoints** — `/api/quotations/{id}/pdf`, `/api/sales-orders/{id}/pdf`, `/api/invoices/{id}/pdf`, `/api/dispatches/{id}/pdf`. Uses reportlab. Branded letterhead, line-item table, totals, optional dispatch metadata, INR-equivalent footer when foreign currency.
- **Multi-currency** — `currency` (INR/USD/AED/EUR/GBP) + `exchange_rate` fields on quotation, sales order, invoice. UI hides exchange-rate when INR.
- **Refactored backend** — server.py shrunk from ~1,000 → ~75 lines. All logic in `core/` + `routers/`.

## Test Status
- Backend: 39 / 39 pytest tests pass (20 regression + 19 new).
- Frontend: smoke test green (login + all routes + ImageUploader + currency selector + PDF download).

## Backlog (P1)
- Email/PDF auto-dispatch (Resend / SendGrid integration) — deferred at user request.
- Camera-based barcode scanner for warehouse staff.

## Backlog (P2)
- Buyer portal (customer self-service).
- Salesperson commission report.
- Push notifications (PWA).
- 2FA / brute-force lockout.

## Auth / Test Credentials
See `/app/memory/test_credentials.md`.
