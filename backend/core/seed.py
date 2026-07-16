import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func

from .auth_utils import hash_password, verify_password
from .db import get_session
from .schema import User, Godown, Product, Customer, Vendor, RateTable, Lead
from .utils import new_id, now_iso


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == admin_email))
        existing = result.scalars().first()
        if not existing:
            session.add(User(
                id=new_id(),
                name="Administrator",
                email=admin_email,
                phone="+91 9876543210",
                role="admin",
                password_hash=hash_password(admin_password),
                created_at=now_iso(),
            ))
        
        elif not verify_password(admin_password, existing.password_hash or ""):
            
            existing.password_hash = hash_password(admin_password)


async def seed_default_categories(session):
    from .schema import ProductCategory
    cats = ["Cuplock", "Ringlock", "Accessories", "Planks", "Raw Material", "Finished Goods"]
    for cat in cats:
        result = await session.execute(
            select(ProductCategory).where(
                func.lower(ProductCategory.name) == cat.lower()
            )
        )
        if not result.scalars().first():
            session.add(ProductCategory(
                id=new_id(),
                name=cat,
                created_at=now_iso(),
                updated_at=now_iso(),
            ))


async def seed_default_coa() -> bool:
    """Seed default Chart of Accounts if the table is empty. Returns True if already present."""
    from .schema import ChartOfAccount
    async with get_session() as session:
        count = (await session.execute(select(func.count()).select_from(ChartOfAccount))).scalar_one()
        if count:
            return True
        now = now_iso()
        default_accounts = [
            # ASSETS
            ("1001", "Cash in Hand", "ASSET"),
            ("1002", "Bank Account - Primary", "ASSET"),
            ("1003", "Petty Cash", "ASSET"),
            ("1100", "Accounts Receivable", "ASSET"),
            ("1200", "Inventory", "ASSET"),
            ("1300", "Prepaid Expenses", "ASSET"),
            ("1400", "Fixed Assets", "ASSET"),
            ("1401", "Plant & Machinery", "ASSET"),
            ("1402", "Vehicles", "ASSET"),
            ("1500", "GST Input Tax Credit", "ASSET"),
            # LIABILITIES
            ("2001", "Accounts Payable", "LIABILITY"),
            ("2002", "GST Payable", "LIABILITY"),
            ("2003", "CGST Payable", "LIABILITY"),
            ("2004", "SGST Payable", "LIABILITY"),
            ("2005", "IGST Payable", "LIABILITY"),
            ("2006", "TDS Payable", "LIABILITY"),
            ("2100", "Short-Term Loans", "LIABILITY"),
            ("2200", "Long-Term Loans", "LIABILITY"),
            ("2300", "Salary Payable", "LIABILITY"),
            # EQUITY
            ("3001", "Owner's Capital", "EQUITY"),
            ("3002", "Retained Earnings", "EQUITY"),
            ("3003", "Current Year Profit/Loss", "EQUITY"),
            # INCOME
            ("4001", "Sales Revenue", "INCOME"),
            ("4002", "Export Revenue", "INCOME"),
            ("4003", "Service Income", "INCOME"),
            ("4004", "Interest Income", "INCOME"),
            ("4005", "Other Income", "INCOME"),
            # EXPENSES
            ("5001", "Cost of Goods Sold", "EXPENSE"),
            ("5002", "Purchase Expenses", "EXPENSE"),
            ("5003", "Salaries & Wages", "EXPENSE"),
            ("5004", "Rent Expense", "EXPENSE"),
            ("5005", "Utilities Expense", "EXPENSE"),
            ("5006", "Transport & Logistics", "EXPENSE"),
            ("5007", "Marketing & Advertising", "EXPENSE"),
            ("5008", "Office Supplies", "EXPENSE"),
            ("5009", "Bank Charges", "EXPENSE"),
            ("5010", "Depreciation", "EXPENSE"),
            ("5011", "Miscellaneous Expenses", "EXPENSE"),
        ]
        for code, name, acct_type in default_accounts:
            session.add(ChartOfAccount(
                id=new_id(), code=code, name=name, account_type=acct_type,
                is_active=True, opening_balance=0, currency="INR", tags=[],
                created_at=now, updated_at=now,
            ))
    return False


async def seed_demo_data():
    async with get_session() as session:
        result = await session.execute(select(Godown))
        if not result.scalars().first():
            gd1 = Godown(id=new_id(), name="Main Warehouse - Pune", location="Pune, MH", created_at=now_iso(), updated_at=now_iso())
            gd2 = Godown(id=new_id(), name="Export Yard - Mumbai", location="Mumbai, MH", created_at=now_iso(), updated_at=now_iso())
            session.add(gd1)
            session.add(gd2)
            await session.flush()

        await seed_default_categories(session)

        result = await session.execute(select(Product))
        if not result.scalars().first():
            now = now_iso()
            prods = [
                Product(id=new_id(), name="Cuplock Vertical 3.0m", sku="CV-3000", category="Cuplock", unit="pcs", cost_price=1200, selling_price=1650, quantity=320, low_stock_threshold=100, hsn_code="7308", gst_rate=18.0, created_at=now, updated_at=now),
                Product(id=new_id(), name="Cuplock Ledger 1.5m", sku="CL-1500", category="Cuplock", unit="pcs", cost_price=480, selling_price=690, quantity=540, low_stock_threshold=200, hsn_code="7308", gst_rate=18.0, created_at=now, updated_at=now),
                Product(id=new_id(), name="Adjustable Base Jack 600mm", sku="ABJ-600", category="Accessories", unit="pcs", cost_price=320, selling_price=480, quantity=80, low_stock_threshold=100, hsn_code="7308", gst_rate=18.0, created_at=now, updated_at=now),
                Product(id=new_id(), name="U-Head Jack 600mm", sku="UHJ-600", category="Accessories", unit="pcs", cost_price=340, selling_price=510, quantity=210, low_stock_threshold=80, hsn_code="7308", gst_rate=18.0, created_at=now, updated_at=now),
                Product(id=new_id(), name="Steel Plank 2.5m", sku="SP-2500", category="Planks", unit="pcs", cost_price=880, selling_price=1180, quantity=45, low_stock_threshold=50, hsn_code="7308", gst_rate=18.0, created_at=now, updated_at=now),
                Product(id=new_id(), name="Ringlock Standard 2.0m", sku="RL-2000", category="Ringlock", unit="pcs", cost_price=980, selling_price=1380, quantity=180, low_stock_threshold=60, hsn_code="7308", gst_rate=18.0, created_at=now, updated_at=now),
            ]
            for p in prods:
                session.add(p)

        result = await session.execute(select(Customer))
        if not result.scalars().first():
            now = now_iso()
            for c in [
                Customer(id=new_id(), name="Rajesh Khanna", company="Skyline Builders Pvt Ltd", email="rajesh@skyline.in", phone="+919876512345", country="India", address="Mumbai, MH", gstin="27ABCDE1234F1Z5", created_at=now, updated_at=now),
                Customer(id=new_id(), name="Ahmed Al-Mansouri", company="Gulf Construction LLC", email="ahmed@gulfcon.ae", phone="+971501234567", country="UAE", address="Dubai, UAE", created_at=now, updated_at=now),
                Customer(id=new_id(), name="Priya Mehta", company="Mehta Infra", email="priya@mehta.in", phone="+919812345600", country="India", address="Ahmedabad, GJ", gstin="24XYZAB1234C1Z2", created_at=now, updated_at=now),
            ]:
                session.add(c)

        result = await session.execute(select(Vendor))
        if not result.scalars().first():
            now = now_iso()
            for v in [
                Vendor(id=new_id(), name="Vikram Singh", company="JSW Steel Ltd", email="sales@jsw.com", phone="+919811112222", address="Mumbai", gstin="27JSWST1234F1Z5", created_at=now, updated_at=now),
                Vendor(id=new_id(), name="Mohammed Khan", company="Tata Steel", email="khan@tata.com", phone="+919833334444", address="Jamshedpur", gstin="20TATA1234F1Z5", created_at=now, updated_at=now),
            ]:
                session.add(v)

        result = await session.execute(select(RateTable))
        if not result.scalars().first():
            now = now_iso()
            for rt in [
                RateTable(id=new_id(), key="job_work_return_window_inputs", value=365, description="Job work return window for inputs (Rule 45 CGST)", effective_from="2017-07-01", created_at=now, updated_at=now),
                RateTable(id=new_id(), key="job_work_return_window_capital_goods", value=1095, description="Job work return window for capital goods (Rule 45 CGST)", effective_from="2017-07-01", created_at=now, updated_at=now),
            ]:
                session.add(rt)

        result = await session.execute(select(Lead))
        if not result.scalars().first():
            now = now_iso()
            for lead in [
                Lead(id=new_id(), company_name="Emirates Build Co.", contact_person="Faisal Ahmed", country="UAE", email="faisal@emiratesbuild.ae", phone="+971502223344", source="Trade Show", interested_in="Cuplock System 50T", estimated_value=4500000, status="QUOTED", notes="Wants delivery in 30 days", next_follow_up=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(), created_at=now, updated_at=now),
                Lead(id=new_id(), company_name="L&T Construction", contact_person="Sandeep Rao", country="India", email="sandeep@lnt.in", phone="+919811223344", source="Referral", interested_in="Ringlock Scaffolding", estimated_value=1800000, status="CONTACTED", notes="Site visit pending", next_follow_up=(datetime.now(timezone.utc) + timedelta(days=5)).isoformat(), created_at=now, updated_at=now),
                Lead(id=new_id(), company_name="Saudi Bin Ladin Group", contact_person="Yusuf Al-Saud", country="Saudi Arabia", email="yusuf@sblg.sa", phone="+966501112233", source="Website", interested_in="Steel Planks bulk", estimated_value=9200000, status="NEW", notes="Initial inquiry", next_follow_up=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), created_at=now, updated_at=now),
                Lead(id=new_id(), company_name="Reliance Industries", contact_person="Anil Patel", country="India", email="anil@ril.in", phone="+919898989898", source="Cold Call", interested_in="Custom scaffolding for refinery", estimated_value=6700000, status="WON", notes="Order confirmed", created_at=now, updated_at=now),
            ]:
                session.add(lead)
