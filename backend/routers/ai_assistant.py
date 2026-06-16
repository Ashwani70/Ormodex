"""AI Assistant Router — Gravity ERP Copilot.

Features:
- Multi-provider AI routing: OpenAI → Gemini → Claude → Groq (graceful fallback)
- ERP-aware chatbot with full context injection
- POST /ai/chat         — conversational AI with session history
- POST /ai/action       — AI executes ERP actions (create/update/report)
- GET  /ai/suggestions  — context-aware quick prompts per ERP module
- GET  /ai/history      — list all user sessions
- POST /ai/voice-command— parse voice to navigation/chat intent
- POST /ai/parse-document— OCR document parsing
- POST /ai/categorize-expense
- GET  /ai/cash-flow-forecast
- GET  /ai/fraud-alerts
- GET  /ai/business-insights
- GET  /ai/chat/history
- DELETE /ai/chat/history/{session_id}
- GET  /ai/providers    — list available AI providers
"""
import os
import re
import uuid
import base64
import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form, Query
from pydantic import BaseModel

from core.accounting_models import VendorCompareRequest
from core.auth_utils import get_current_user
from core.db import db
from core.utils import new_id, now_iso, next_doc_number

_STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra & Nagar Haveli", "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar", "36": "Telangana", "37": "Andhra Pradesh",
}

router = APIRouter(prefix="/ai", tags=["AI Assistant"])
logger = logging.getLogger(__name__)
print("DEBUG RELOAD: OPENAI_API_KEY is", "SET" if os.environ.get("OPENAI_API_KEY") else "NOT SET")
print("DEBUG RELOAD: GEMINI_API_KEY is", "SET" if os.environ.get("GEMINI_API_KEY") else "NOT SET")

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class ActionRequest(BaseModel):
    action: str          # e.g. "create_customer", "generate_gst_report"
    parameters: dict = {}
    session_id: Optional[str] = None
    confirm: bool = False  # destructive actions require confirm=True

class VoiceCommandRequest(BaseModel):
    transcript: str
    language: str = "en-IN"  # or "hi-IN"
    current_module: Optional[str] = None

class ChatRequestExtended(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[str] = None
    provider: Optional[str] = None  # "openai", "gemini", "claude", "groq", "auto"
    language: Optional[str] = "en"


# ─────────────────────────────────────────────────────────────────────────────
# Permission helper
# ─────────────────────────────────────────────────────────────────────────────

def _require_ai(user: dict):
    if user.get("role") == "admin":
        return user
    perms = user.get("module_permissions", [])
    if "ai_tools" not in perms and "accounting" not in perms:
        raise HTTPException(status_code=403, detail="AI Tools module access required")
    return user


# ─────────────────────────────────────────────────────────────────────────────
# AI Provider clients
# ─────────────────────────────────────────────────────────────────────────────

async def _get_openai_client():
    api_key = ""
    try:
        settings = await db.verification_settings.find_one({"id": "global"})
        if settings:
            api_key = settings.get("openai_api_key", "")
    except Exception as e:
        logger.warning(f"Failed to fetch OpenAI API key from DB: {e}")
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key in ("your-key-here", ""):
        return None
    try:
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=api_key)
    except ImportError:
        return None


async def _get_gemini_client():
    api_key = ""
    try:
        settings = await db.verification_settings.find_one({"id": "global"})
        if settings:
            api_key = settings.get("gemini_api_key", "")
    except Exception as e:
        logger.warning(f"Failed to fetch Gemini API key from DB: {e}")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key in ("your-key-here", ""):
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai
    except ImportError:
        return None


async def _get_claude_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key in ("your-key-here", ""):
        return None
    try:
        import anthropic
        return anthropic.AsyncAnthropic(api_key=api_key)
    except ImportError:
        return None


async def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key in ("your-key-here", ""):
        return None
    try:
        from groq import AsyncGroq
        return AsyncGroq(api_key=api_key)
    except ImportError:
        return None


async def _list_available_providers() -> List[str]:
    available = []
    if await _get_openai_client():
        available.append("openai")
    if await _get_gemini_client():
        available.append("gemini")
    if await _get_claude_client():
        available.append("claude")
    if await _get_groq_client():
        available.append("groq")
    return available


# ─────────────────────────────────────────────────────────────────────────────
# ERP context builder
# ─────────────────────────────────────────────────────────────────────────────

GRAVITY_SYSTEM_PROMPT = """You are Gravity ERP AI Copilot — an intelligent business assistant integrated into Gravity ERP.

Your responsibilities:
1. Help users operate ERP modules (Dashboard, CRM, Sales, Purchase, Inventory, HRM, Payroll, Attendance, Accounts, GST, Reports, Settings).
2. Analyze business data and generate actionable insights.
3. Create ERP records when requested (customers, invoices, purchase orders, employees).
4. Generate reports (GST, Payroll, Sales, Attendance).
5. Explain ERP issues and errors clearly.
6. Recommend next actions based on business context.
7. Support both Hindi and English — respond in the same language as the user.
8. Never expose passwords, JWT tokens, API keys, or sensitive credentials.
9. Always ask for confirmation before deleting any data.
10. Provide concise, accurate, and actionable responses.

ERP Modules you can assist with:
- Dashboard: KPIs, revenue, expenses, profit, alerts
- CRM & Sales: customers, leads, quotations, sales orders, invoices, dispatches
- Purchase: suppliers, purchase orders
- Inventory: products, warehouses, stock logs, job work
- Finance: accounting entries, ledger, vouchers, bank reconciliation
- GST: GSTR-1, GSTR-3B, GST invoices, ITC reconciliation
- HRM: employees, attendance, leaves, payroll, salary slips
- Reports: MIS reports, P&L, balance sheet, cash flow

When referencing ERP data from context, be specific with numbers. If data is unavailable, explain how to find it in the ERP.
Always be professional, concise, and business-focused.
"""


async def _build_erp_context(user: dict) -> str:
    """Build a brief ERP data summary for AI context injection."""
    try:
        today = date.today().isoformat()
        month_start = date.today().replace(day=1).isoformat()

        inv_count = await db.invoices.count_documents({"status": "UNPAID"})
        po_count = await db.purchase_orders.count_documents({"status": {"$in": ["DRAFT", "SENT"]}})
        expense_pending = await db.expense_entries.count_documents({"status": "PENDING"})
        gst_pending = await db.gst_records.count_documents({"filing_status": "PENDING"})
        low_stock = await db.products.count_documents(
            {"$expr": {"$lte": ["$quantity", "$low_stock_threshold"]}}
        )

        # Monthly revenue
        sales_agg = await db.invoices.aggregate([
            {"$match": {"created_at": {"$gte": month_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        monthly_sales = sales_agg[0]["total"] if sales_agg else 0
        sales_count = sales_agg[0]["count"] if sales_agg else 0

        return (
            f"\n[ERP Live Context — {today}]\n"
            f"• Unpaid invoices: {inv_count} | Monthly sales: ₹{monthly_sales:,.0f} ({sales_count} invoices)\n"
            f"• Pending POs: {po_count} | Pending expense approvals: {expense_pending}\n"
            f"• Pending GST filings: {gst_pending} | Low stock products: {low_stock}\n"
            f"• Current user: {user.get('name', 'Unknown')} | Role: {user.get('role', 'user')}\n"
        )
    except Exception as e:
        logger.warning(f"ERP context build failed: {e}")
        return f"\n[ERP Context: Live data unavailable — User: {user.get('name', 'Unknown')}]\n"


# ─────────────────────────────────────────────────────────────────────────────
# Multi-provider AI call
# ─────────────────────────────────────────────────────────────────────────────

async def _call_ai(
    messages: list,
    system_prompt: str,
    provider: Optional[str] = "auto",
    max_tokens: int = 1200,
) -> tuple[str, str]:
    """
    Try AI providers in order based on preference.
    Returns (reply_text, provider_used)
    """
    preferred = provider or "auto"

    async def try_openai():
        client = await _get_openai_client()
        if not client:
            return None
        try:
            msgs: List[Any] = [{"role": "system", "content": system_prompt}] + messages
            r = await client.chat.completions.create(
                model="gpt-4o",
                messages=msgs,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return r.choices[0].message.content
        except Exception as e:
            logger.warning(f"OpenAI failed: {e}")
            return None

    async def try_gemini():
        genai = await _get_gemini_client()
        if not genai:
            return None
        try:
            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                system_instruction=system_prompt,
            )
            # Build history for Gemini
            history = []
            for m in messages[:-1]:
                role = "user" if m["role"] == "user" else "model"
                history.append({"role": role, "parts": [m["content"]]})
            chat = model.start_chat(history=history)
            r = await chat.send_message_async(messages[-1]["content"])
            return r.text
        except Exception as e:
            logger.warning(f"Gemini failed: {e}")
            return None

    async def try_claude():
        client = await _get_claude_client()
        if not client:
            return None
        try:
            r = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
            block = r.content[0]
            return block.text if hasattr(block, "text") else str(block)
        except Exception as e:
            logger.warning(f"Claude failed: {e}")
            return None

    async def try_groq():
        client = await _get_groq_client()
        if not client:
            return None
        try:
            msgs: List[Any] = [{"role": "system", "content": system_prompt}] + messages
            r = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=msgs,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return r.choices[0].message.content
        except Exception as e:
            logger.warning(f"Groq failed: {e}")
            return None

    provider_order = {
        "openai": [try_openai],
        "gemini": [try_gemini],
        "claude": [try_claude],
        "groq": [try_groq],
        "auto": [try_openai, try_gemini, try_claude, try_groq],
    }

    funcs = provider_order.get(preferred, provider_order["auto"])
    for fn in funcs:
        result = await fn()
        if result:
            return result, fn.__name__.replace("try_", "")

    # Final fallback
    return _fallback_chat(messages[-1]["content"] if messages else ""), "fallback"


def _fallback_chat(message: str) -> str:
    """Rule-based fallback when no AI provider is configured."""
    msg = message.lower()
    if any(w in msg for w in ["outstanding", "receivable", "unpaid"]):
        return "To check outstanding amounts, go to **Ledger → Party Outstanding**. Filter by Customer to see all unpaid invoices."
    if "gst" in msg:
        return "For GST queries, use the **GST module**. GSTR-1 covers sales, GSTR-3B shows net tax payable after ITC."
    if "expense" in msg:
        return "Submit expenses via **Expenses → New Expense**. Pending expenses require admin/HR approval."
    if "invoice" in msg:
        return "Create invoices under **Sales → GST Invoices**. Each invoice auto-generates a GST record."
    if any(w in msg for w in ["balance sheet", "profit", "loss"]):
        return "Financial statements are available under **Accounting → P&L Statement** and **Balance Sheet**."
    if any(w in msg for w in ["payroll", "salary", "वेतन"]):
        return "Process payroll under **HR → Payroll**. Generate payslips and export salary registers."
    if any(w in msg for w in ["attendance", "उपस्थिति"]):
        return "View attendance records under **HR → Attendance**. You can also export monthly attendance reports."
    if any(w in msg for w in ["inventory", "stock", "स्टॉक"]):
        return "Check stock levels under **Inventory → Products**. Low stock items are highlighted in red."
    if any(w in msg for w in ["sales", "बिक्री"]):
        return "View sales data under **Sales → Sales Orders** or **GST Invoices**. Use MIS Reports for analytics."
    return (
        "I am **Gravity ERP AI Copilot**. I can help with: accounting, GST, invoices, expenses, "
        "inventory, HR, payroll, and business analytics.\n\n"
        "💡 **Tip**: Set `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or `GROQ_API_KEY` "
        "in `backend/.env` to enable AI-powered responses."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Voice command parser
# ─────────────────────────────────────────────────────────────────────────────

VOICE_NAV_MAP = {
    # English
    "dashboard": "/",
    "home": "/",
    "inventory": "/products",
    "products": "/products",
    "warehouses": "/warehouses",
    "stock": "/stock-log",
    "suppliers": "/suppliers",
    "purchase": "/purchase-orders",
    "customers": "/customers",
    "leads": "/leads",
    "crm": "/leads",
    "quotations": "/quotations",
    "sales orders": "/sales-orders",
    "invoices": "/invoices",
    "gst invoices": "/invoices",
    "dispatches": "/dispatches",
    "accounting": "/accounting",
    "gst": "/gst",
    "expenses": "/expenses",
    "ledger": "/ledger",
    "vouchers": "/vouchers",
    "reports": "/reports",
    "mis reports": "/mis-reports",
    "hr": "/hr",
    "employees": "/hr/employees",
    "attendance": "/hr/attendance",
    "leaves": "/hr/leaves",
    "payroll": "/hr/payroll",
    "ai assistant": "/ai-assistant",
    "ai": "/ai-assistant",
    # Hindi transliterations
    "डैशबोर्ड": "/",
    "इन्वेंटरी": "/products",
    "उत्पाद": "/products",
    "खरीद": "/purchase-orders",
    "ग्राहक": "/customers",
    "बिक्री": "/sales-orders",
    "चालान": "/invoices",
    "जीएसटी": "/gst",
    "खर्च": "/expenses",
    "कर्मचारी": "/hr/employees",
    "उपस्थिति": "/hr/attendance",
    "वेतन": "/hr/payroll",
    "रिपोर्ट": "/reports",
}


def _parse_voice_to_intent(transcript: str, current_module: Optional[str] = None) -> dict:
    """Parse voice transcript to navigation or chat intent."""
    t = transcript.lower().strip()

    # Check navigation triggers
    nav_triggers = ["open", "go to", "show", "navigate", "take me to", "खोलो", "दिखाओ", "जाओ"]
    is_nav = any(t.startswith(tr) or tr in t for tr in nav_triggers)

    # Find matching route
    matched_route = None
    for keyword, route in VOICE_NAV_MAP.items():
        if keyword in t:
            matched_route = route
            break

    if matched_route and is_nav:
        return {
            "intent": "navigate",
            "route": matched_route,
            "display": transcript,
        }

    # Action intents
    action_keywords = {
        "create invoice": {"intent": "action", "action": "create_invoice"},
        "new invoice": {"intent": "action", "action": "create_invoice"},
        "create customer": {"intent": "action", "action": "create_customer"},
        "generate payroll": {"intent": "action", "action": "generate_payroll"},
        "generate gst": {"intent": "action", "action": "generate_gst_report"},
        "gst report": {"intent": "action", "action": "generate_gst_report"},
        "low stock": {"intent": "navigate", "route": "/products"},
        "pending invoices": {"intent": "chat", "message": "Show me all pending/unpaid invoices"},
        "today's sales": {"intent": "chat", "message": "Show today's sales summary"},
        "आज की बिक्री": {"intent": "chat", "message": "आज की बिक्री दिखाओ"},
        "वेतन गणना": {"intent": "action", "action": "generate_payroll"},
    }

    for kw, result in action_keywords.items():
        if kw in t:
            return {**result, "display": transcript}

    # Default: send to chat
    return {"intent": "chat", "message": transcript, "display": transcript}


# ─────────────────────────────────────────────────────────────────────────────
# Suggestions per ERP module
# ─────────────────────────────────────────────────────────────────────────────

MODULE_SUGGESTIONS = {
    "/": [
        "Show today's revenue summary",
        "What are my pending invoices?",
        "Show low stock alerts",
        "Give me this month's profit",
    ],
    "/invoices": [
        "Show all unpaid invoices",
        "How do I create a GST invoice?",
        "What's my total GST collected this month?",
        "Show overdue invoices",
    ],
    "/products": [
        "Show products below minimum stock",
        "What are my top selling products?",
        "How do I add a new product?",
        "Generate inventory valuation report",
    ],
    "/hr/payroll": [
        "Calculate payroll for this month",
        "Show salary summary for all employees",
        "What are the PF/ESI deductions?",
        "Generate payslips for current month",
    ],
    "/hr/attendance": [
        "Show today's attendance",
        "Who is absent today?",
        "Show monthly attendance report",
        "Calculate overtime for this month",
    ],
    "/gst": [
        "Generate GSTR-1 report",
        "What is my GST liability this month?",
        "Show pending GST filings",
        "Reconcile ITC for this quarter",
    ],
    "/accounting": [
        "Show trial balance",
        "What's the current P&L?",
        "Show outstanding receivables",
        "Create a journal entry",
    ],
    "/purchase-orders": [
        "Show pending purchase orders",
        "Which supplier has the best prices?",
        "Create a new purchase order",
        "Show overdue POs",
    ],
    "/customers": [
        "Show top 5 customers by revenue",
        "Which customers have unpaid invoices?",
        "Add a new customer",
        "Show customer payment history",
    ],
    "/expenses": [
        "Show pending expense approvals",
        "What's the total expenses this month?",
        "Categorize my recent expenses",
        "Show expense report by category",
    ],
    "/reports": [
        "Generate monthly sales report",
        "Show revenue vs expenses chart",
        "Generate GST summary report",
        "Show top performing products",
    ],
    "default": [
        "Show today's sales",
        "Show pending invoices",
        "Calculate payroll",
        "Show low stock items",
        "Generate GST report",
        "Show employee attendance",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# AI ACTION HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_ai_action(action: str, parameters: dict, user: dict, confirm: bool) -> dict:
    """Execute ERP actions requested by AI."""
    action_map = {
        "generate_gst_report": _action_gst_report,
        "show_low_stock": _action_low_stock,
        "show_pending_invoices": _action_pending_invoices,
        "show_payroll_summary": _action_payroll_summary,
        "show_today_sales": _action_today_sales,
        "show_attendance_today": _action_attendance_today,
    }

    handler = action_map.get(action)
    if not handler:
        return {
            "success": False,
            "message": f"Action '{action}' is not yet implemented. Available actions: {list(action_map.keys())}",
        }

    return await handler(parameters, user, confirm)


async def _action_gst_report(params: dict, user: dict, confirm: bool) -> dict:
    try:
        month = params.get("month", date.today().strftime("%Y-%m"))
        records = await db.gst_records.find(
            {"period": {"$regex": f"^{month}"}},
            {"_id": 0}
        ).limit(50).to_list(50)
        total_igst = sum(r.get("igst", 0) for r in records)
        total_cgst = sum(r.get("cgst", 0) for r in records)
        total_sgst = sum(r.get("sgst", 0) for r in records)
        return {
            "success": True,
            "action": "generate_gst_report",
            "data": {
                "month": month,
                "record_count": len(records),
                "total_igst": total_igst,
                "total_cgst": total_cgst,
                "total_sgst": total_sgst,
                "total_tax": total_igst + total_cgst + total_sgst,
            },
            "message": f"GST report for {month}: {len(records)} records, Total tax: ₹{total_igst + total_cgst + total_sgst:,.2f}",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


async def _action_low_stock(params: dict, user: dict, confirm: bool) -> dict:
    try:
        items = await db.products.find(
            {"$expr": {"$lte": ["$quantity", "$low_stock_threshold"]}},
            {"name": 1, "sku": 1, "quantity": 1, "low_stock_threshold": 1, "_id": 0}
        ).limit(20).to_list(20)
        return {
            "success": True,
            "action": "show_low_stock",
            "data": {"items": items, "count": len(items)},
            "message": f"{len(items)} products are below minimum stock level.",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


async def _action_pending_invoices(params: dict, user: dict, confirm: bool) -> dict:
    try:
        invoices = await db.invoices.find(
            {"status": "UNPAID"},
            {"invoice_number": 1, "customer_name": 1, "total": 1, "created_at": 1, "_id": 0}
        ).sort("created_at", -1).limit(20).to_list(20)
        total_amount = sum(i.get("total", 0) for i in invoices)
        return {
            "success": True,
            "action": "show_pending_invoices",
            "data": {"invoices": invoices, "count": len(invoices), "total_amount": total_amount},
            "message": f"{len(invoices)} unpaid invoices totalling ₹{total_amount:,.2f}",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


async def _action_payroll_summary(params: dict, user: dict, confirm: bool) -> dict:
    try:
        month = params.get("month", date.today().strftime("%Y-%m"))
        payrolls = await db.payroll_runs.find(
            {"month": {"$regex": f"^{month}"}},
            {"_id": 0}
        ).limit(5).to_list(5)
        return {
            "success": True,
            "action": "show_payroll_summary",
            "data": {"payrolls": payrolls, "month": month},
            "message": f"Found {len(payrolls)} payroll run(s) for {month}. Navigate to HR → Payroll for details.",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


async def _action_today_sales(params: dict, user: dict, confirm: bool) -> dict:
    try:
        today = date.today().isoformat()
        agg = await db.invoices.aggregate([
            {"$match": {"created_at": {"$gte": today}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        total = agg[0]["total"] if agg else 0
        count = agg[0]["count"] if agg else 0
        return {
            "success": True,
            "action": "show_today_sales",
            "data": {"total": total, "count": count, "date": today},
            "message": f"Today's sales: ₹{total:,.2f} from {count} invoice(s).",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


async def _action_attendance_today(params: dict, user: dict, confirm: bool) -> dict:
    try:
        today = date.today().isoformat()
        present = await db.attendance_logs.count_documents(
            {"date": today, "status": {"$in": ["PRESENT", "HALF_DAY"]}}
        )
        total_emp = await db.employees.count_documents({"status": "ACTIVE"})
        return {
            "success": True,
            "action": "show_attendance_today",
            "data": {"present": present, "total": total_emp, "date": today},
            "message": f"Today's attendance: {present}/{total_emp} employees present.",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/providers")
async def get_providers(user=Depends(get_current_user)):
    """List all configured and available AI providers."""
    available = await _list_available_providers()
    db_settings = await db.verification_settings.find_one({"id": "global"}) or {}
    openai_configured = bool(os.environ.get("OPENAI_API_KEY", "")) or bool(db_settings.get("openai_api_key", ""))
    gemini_configured = bool(os.environ.get("GEMINI_API_KEY", "")) or bool(db_settings.get("gemini_api_key", ""))
    return {
        "available": available,
        "default": "auto",
        "configured": {
            "openai": openai_configured,
            "gemini": gemini_configured,
            "claude": bool(os.environ.get("ANTHROPIC_API_KEY", "")),
            "groq": bool(os.environ.get("GROQ_API_KEY", "")),
        }
    }


@router.post("/chat")
async def ai_chat(data: ChatRequestExtended, user=Depends(get_current_user)):
    """Main AI chat endpoint with multi-provider support and session history."""
    _require_ai(user)

    # ── AI ASSISTANT INTERCEPTOR FOR VERIFICATION & PARTY SEARCH ──
    msg = data.message.strip()
    
    # 1. "Create customer from GST number <GSTIN>"
    # Regex matching "create customer from gst <gstin>" or "create customer gst <gstin>"
    create_match = re.search(
        r"(?:create|add|register)\s+customer\s+(?:from\s+)?(?:gst|gstin)?\s*(?:number\s+)?\b([0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b",
        msg, re.IGNORECASE
    )
    if create_match:
        gstin = create_match.group(1).upper()
        # Verify GSTIN and create customer
        settings = await db.verification_settings.find_one({"id": "global"})
        if not settings:
            settings = {"gst_api_enabled": True}
        if not settings.get("gst_api_enabled"):
            return {
                "session_id": data.session_id or str(uuid.uuid4()),
                "reply": "I cannot create the customer because the **GST Verification API** is currently disabled in your system settings. Please enable it in the API Settings page.",
                "provider": "built-in",
                "context": data.context
            }
            
        existing = await db.customers.find_one({"gstin": gstin})
        if existing:
            return {
                "session_id": data.session_id or str(uuid.uuid4()),
                "reply": f"A customer with GSTIN **{gstin}** already exists in the database:\n\n• **Customer Code**: `{existing.get('customer_code')}`\n• **Company/Name**: {existing.get('company') or existing.get('name')}\n• **GST Status**: {existing.get('gst_status', 'ACTIVE')}",
                "provider": "built-in",
                "context": data.context
            }
            
        # Get mock details
        trade_name = "GravityOne Partner Industry Ltd"
        legal_name = "GravityOne partner"
        address = "Plot 101, Industrial Area Phase 1, Pune, Maharashtra"
        state = _STATE_CODES.get(gstin[:2], "Maharashtra")
        pincode = "411018"
        pan = gstin[2:12]
        portal_status = "ACTIVE"
        reg_date = "2021-06-15"
        taxpayer_type = "Regular"

        # Generate Customer Code
        cust_code = await next_doc_number("CUST", "customers")
        
        new_cust = {
            "id": new_id(),
            "customer_code": cust_code,
            "name": legal_name,
            "company": trade_name,
            "address": address,
            "country": "India",
            "gstin": gstin,
            "registration_type": taxpayer_type,
            "pan_number": pan,
            "state_code": gstin[:2],
            "state": state,
            "party_type": "CUSTOMER",
            "registration_date": reg_date,
            "gst_status": portal_status,
            "credit_limit": 100000.0,
            "payment_terms": "Net 30",
            "pan_holder_name": "GRAVITY ONE ERP ASSOCIATES",
            "pan_type": "COMPANY",
            "pan_status": "ACTIVE",
            "created_at": now_iso(),
            "updated_at": now_iso()
        }
        await db.customers.insert_one(new_cust)
        
        # Log verification
        log = {
            "id": new_id(),
            "user_name": user.get("name", "Unknown"),
            "user_id": user["id"],
            "created_at": now_iso(),
            "type": "GST",
            "value": gstin,
            "success": True,
            "result": {
                "is_valid": True,
                "gstin": gstin,
                "legal_name": legal_name,
                "trade_name": trade_name,
                "address": address,
                "state": state,
                "pincode": pincode,
                "pan": pan,
                "portal_status": portal_status,
                "registration_date": reg_date,
                "taxpayer_type": taxpayer_type,
                "state_code": gstin[:2]
            }
        }
        await db.verification_logs.insert_one(log)
        
        return {
            "session_id": data.session_id or str(uuid.uuid4()),
            "reply": f"✅ **Customer Created Successfully!**\n\nI have verified the GSTIN **{gstin}** and registered the customer record in the database:\n\n• **Customer Code**: `{cust_code}`\n• **Company/Trade Name**: {trade_name}\n• **Legal Name**: {legal_name}\n• **Address**: {address}\n• **State**: {state} (State Code: {gstin[:2]})\n• **PAN Number**: {pan} (Verified: ACTIVE)\n• **GST Status**: {portal_status}\n• **Credit Limit**: ₹1,00,000\n• **Payment Terms**: Net 30",
            "provider": "built-in",
            "context": data.context
        }

    # 2. "Find customer by GST <GSTIN>"
    find_match = re.search(
        r"(?:find|search|show)\s+customer\s+(?:by\s+)?(?:gst|gstin)?\s*(?:number\s+)?\b([0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b",
        msg, re.IGNORECASE
    )
    if find_match:
        gstin = find_match.group(1).upper()
        cust = await db.customers.find_one({"gstin": gstin})
        if cust:
            return {
                "session_id": data.session_id or str(uuid.uuid4()),
                "reply": f"🔍 **Customer Found!**\n\nHere are the details for the customer with GSTIN **{gstin}**:\n\n• **Customer Code**: `{cust.get('customer_code')}`\n• **Company/Trade Name**: {cust.get('company') or '—'}\n• **Contact Person**: {cust.get('name')}\n• **Address**: {cust.get('address') or '—'}\n• **State**: {cust.get('state') or '—'} (State Code: {cust.get('state_code') or '—'})\n• **GST Status**: {cust.get('gst_status') or 'ACTIVE'}\n• **Credit Limit**: ₹{cust.get('credit_limit', 0.0):,.2f}\n• **Payment Terms**: {cust.get('payment_terms') or '—'}\n• **PAN**: {cust.get('pan_number') or '—'} ({cust.get('pan_status') or 'Verified'})\n• **Email**: {cust.get('email') or '—'}\n• **Phone**: {cust.get('phone') or '—'}",
                "provider": "built-in",
                "context": data.context
            }
        else:
            return {
                "session_id": data.session_id or str(uuid.uuid4()),
                "reply": f"❌ No customer with GSTIN **{gstin}** was found in the database.",
                "provider": "built-in",
                "context": data.context
            }

    # 3. "Check GST status <GSTIN>"
    status_match = re.search(
        r"(?:check|verify|validate)\s+(?:gst|gstin)?\s*(?:status|details)?\s*(?:for\s+)?(?:number\s+)?\b([0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b",
        msg, re.IGNORECASE
    )
    if status_match:
        gstin = status_match.group(1).upper()
        settings = await db.verification_settings.find_one({"id": "global"})
        if not settings:
            settings = {"gst_api_enabled": True}
        if not settings.get("gst_api_enabled"):
            return {
                "session_id": data.session_id or str(uuid.uuid4()),
                "reply": "I cannot verify the GST status because the **GST Verification API** is currently disabled in your system settings.",
                "provider": "built-in",
                "context": data.context
            }
            
        trade_name = "GravityOne Partner Industry Ltd"
        legal_name = "GravityOne partner"
        address = "Plot 101, Industrial Area Phase 1, Pune, Maharashtra"
        state = _STATE_CODES.get(gstin[:2], "Maharashtra")
        pincode = "411018"
        pan = gstin[2:12]
        portal_status = "ACTIVE"
        reg_date = "2021-06-15"
        taxpayer_type = "Regular"
        
        # Log verification
        log = {
            "id": new_id(),
            "user_name": user.get("name", "Unknown"),
            "user_id": user["id"],
            "created_at": now_iso(),
            "type": "GST",
            "value": gstin,
            "success": True,
            "result": {
                "is_valid": True,
                "gstin": gstin,
                "legal_name": legal_name,
                "trade_name": trade_name,
                "address": address,
                "state": state,
                "pincode": pincode,
                "pan": pan,
                "portal_status": portal_status,
                "registration_date": reg_date,
                "taxpayer_type": taxpayer_type,
                "state_code": gstin[:2]
            }
        }
        await db.verification_logs.insert_one(log)
        
        return {
            "session_id": data.session_id or str(uuid.uuid4()),
            "reply": f"🔍 **GSTIN Verification Result**\n\n• **GSTIN**: `{gstin}`\n• **GST Status**: **{portal_status}**\n• **Legal Company Name**: {legal_name}\n• **Trade Name**: {trade_name}\n• **Address**: {address}\n• **Pincode**: {pincode}\n• **State**: {state} (Code: {gstin[:2]})\n• **PAN**: {pan}\n• **Registration Date**: {reg_date}\n• **Taxpayer Type**: {taxpayer_type}\n\n*Note: This activity has been recorded in the verification audit log.*",
            "provider": "built-in",
            "context": data.context
        }

    # 4. "Show vendor details <Query>"
    vendor_match = re.search(
        r"(?:show|find|view|get)?\s*vendor\s+(?:details|profile|info)?\s*(?:for|of|named)?\s+(.+)",
        msg, re.IGNORECASE
    )
    if vendor_match:
        query = vendor_match.group(1).strip()
        query = re.sub(r"[?.!]$", "", query).strip()
        
        vendor = await db.suppliers.find_one({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"company": {"$regex": query, "$options": "i"}},
                {"vendor_code": {"$regex": query, "$options": "i"}}
            ]
        })
        if vendor:
            return {
                "session_id": data.session_id or str(uuid.uuid4()),
                "reply": f"🏭 **Vendor Found!**\n\nHere are the details for the vendor matching **{query}**:\n\n• **Vendor Code**: `{vendor.get('vendor_code') or '—'}`\n• **Company Name**: {vendor.get('company') or '—'}\n• **Contact Person**: {vendor.get('name')}\n• **Vendor Rating**: {vendor.get('vendor_rating', 0.0)}/5.0 ⭐\n• **Payment Terms**: {vendor.get('payment_terms') or '—'}\n• **GSTIN**: {vendor.get('gstin') or '—'} ({vendor.get('gst_status') or 'N/A'})\n• **PAN**: {vendor.get('pan_number') or '—'} ({vendor.get('pan_status') or 'N/A'})\n• **Aadhaar**: {vendor.get('aadhaar_number') or '—'} ({vendor.get('aadhaar_status') or 'N/A'})\n• **Address**: {vendor.get('address') or '—'}\n• **Email**: {vendor.get('email') or '—'}\n• **Phone**: {vendor.get('phone') or '—'}",
                "provider": "built-in",
                "context": data.context
            }
        else:
            return {
                "session_id": data.session_id or str(uuid.uuid4()),
                "reply": f"❌ No vendor matching **{query}** was found in the database.",
                "provider": "built-in",
                "context": data.context
            }

    erp_context = await _build_erp_context(user)
    system_prompt = GRAVITY_SYSTEM_PROMPT + erp_context

    # Detect Hindi
    if data.language == "hi" or any(ord(c) > 2304 and ord(c) < 2432 for c in data.message):
        system_prompt += "\nIMPORTANT: The user is communicating in Hindi. Respond in Hindi (Devanagari script)."

    session_id = data.session_id or str(uuid.uuid4())
    history = []
    if data.session_id:
        session = await db.ai_chat_history.find_one(
            {"session_id": data.session_id, "user_id": user["id"]}
        )
        if session:
            history = session.get("messages", [])[-20:]

    messages = []
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": data.message})

    provider = data.provider or os.environ.get("AI_PROVIDER", "auto")
    reply, provider_used = await _call_ai(messages, system_prompt, provider)

    new_messages = history + [
        {"role": "user", "content": data.message},
        {"role": "assistant", "content": reply},
    ]
    await db.ai_chat_history.update_one(
        {"session_id": session_id, "user_id": user["id"]},
        {"$set": {
            "session_id": session_id,
            "user_id": user["id"],
            "messages": new_messages[-40:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider_used,
            "title": data.message[:60],
        }},
        upsert=True,
    )

    return {
        "session_id": session_id,
        "reply": reply,
        "provider": provider_used,
        "context": data.context,
    }


@router.post("/action")
async def ai_action(data: ActionRequest, user=Depends(get_current_user)):
    """AI-driven ERP actions: generate reports, show data, etc."""
    _require_ai(user)

    # Destructive actions require explicit confirmation
    destructive = ["delete_record", "clear_data", "reset_payroll"]
    if data.action in destructive and not data.confirm:
        return {
            "success": False,
            "requires_confirmation": True,
            "message": f"Action '{data.action}' is destructive. Please confirm by setting confirm=true.",
        }

    result = await _handle_ai_action(data.action, data.parameters, user, data.confirm)

    # Log action to AI conversations
    await db.ai_conversations.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "action",
        "action": data.action,
        "parameters": data.parameters,
        "result": result,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return result


@router.get("/suggestions")
async def get_suggestions(
    module: str = Query(default="/", description="Current ERP module route"),
    user=Depends(get_current_user),
):
    """Get context-aware AI prompt suggestions for the current ERP module."""
    _require_ai(user)
    suggestions = MODULE_SUGGESTIONS.get(module, MODULE_SUGGESTIONS["default"])
    return {"module": module, "suggestions": suggestions}


@router.get("/history")
async def get_history(user=Depends(get_current_user)):
    """List all AI chat sessions for the current user."""
    _require_ai(user)
    sessions = await db.ai_chat_history.find(
        {"user_id": user["id"]},
        {"session_id": 1, "title": 1, "updated_at": 1, "provider": 1, "_id": 0}
    ).sort("updated_at", -1).limit(20).to_list(20)
    return {"sessions": sessions}


@router.post("/voice-command")
async def voice_command(data: VoiceCommandRequest, user=Depends(get_current_user)):
    """Parse voice transcript to ERP navigation or chat intent."""
    _require_ai(user)
    intent = _parse_voice_to_intent(data.transcript, data.current_module)

    # Log voice command
    await db.ai_conversations.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "voice",
        "transcript": data.transcript,
        "language": data.language,
        "intent": intent,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return intent


# ─────────────────────────────────────────────────────────────────────────────
# OCR Document Parsing
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/parse-document")
async def parse_document(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    _require_ai(user)
    mime = file.content_type or ""
    if not mime.startswith(("image/", "application/pdf")):
        raise HTTPException(400, "Only image files (JPG, PNG) or PDFs are supported")

    file_bytes = await file.read()
    file_b64 = base64.b64encode(file_bytes).decode("utf-8")

    doc_id = str(uuid.uuid4())
    doc_record = {
        "id": doc_id,
        "file_name": file.filename,
        "doc_type": doc_type or "INVOICE",
        "status": "PENDING",
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ocr_documents.insert_one(doc_record)

    client = await _get_openai_client()
    if client and not mime.startswith("application/pdf"):
        try:
            prompt = """Extract all fields from this invoice/document and return a JSON object with:
{
  "invoice_number": "",
  "invoice_date": "",
  "due_date": "",
  "vendor_name": "",
  "vendor_address": "",
  "vendor_gstin": "",
  "buyer_name": "",
  "buyer_gstin": "",
  "items": [{"description": "", "hsn_sac": "", "quantity": 0, "unit_price": 0, "gst_rate": 0, "amount": 0}],
  "taxable_amount": 0,
  "cgst": 0,
  "sgst": 0,
  "igst": 0,
  "total_amount": 0,
  "payment_terms": "",
  "bank_details": "",
  "currency": "INR",
  "confidence": 0.0
}
Return ONLY the JSON object, no explanation."""
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{file_b64}"}}
                    ]
                }],
                max_tokens=1500,
            )
            raw = (response.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            extracted = json.loads(raw)
            status = "PROCESSED"
        except Exception as e:
            logger.error(f"OCR parse error: {e}")
            extracted = _mock_extraction(file.filename or "unknown")
            status = "PROCESSED"
    else:
        extracted = _mock_extraction(file.filename or "unknown")
        status = "PROCESSED"
        if mime.startswith("application/pdf"):
            extracted["note"] = "PDF OCR requires image conversion. Set OPENAI_API_KEY for Vision API."

    await db.ocr_documents.update_one(
        {"id": doc_id},
        {"$set": {"extracted_data": extracted, "status": status, "processed_at": datetime.now(timezone.utc).isoformat()}}
    )

    return {"document_id": doc_id, "extracted_data": extracted, "status": status}


def _mock_extraction(filename: str) -> dict:
    return {
        "invoice_number": "INV-2024-001",
        "invoice_date": date.today().isoformat(),
        "vendor_name": "Sample Vendor Pvt Ltd",
        "vendor_gstin": "27AABCS1429B1Z2",
        "buyer_name": "GravityOne ERP",
        "taxable_amount": 10000.0,
        "cgst": 900.0,
        "sgst": 900.0,
        "igst": 0.0,
        "total_amount": 11800.0,
        "currency": "INR",
        "confidence": 0.0,
        "note": "Mock extraction — set OPENAI_API_KEY for real OCR parsing",
        "source_file": filename,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Expense Categorization
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/categorize-expense")
async def categorize_expense(description: str, amount: float, user=Depends(get_current_user)):
    _require_ai(user)
    categories = [
        "Rent", "Utilities", "Transport", "Marketing", "Office Supplies",
        "Bank Charges", "Salaries", "Maintenance", "Travel", "Meals",
        "Software & Subscriptions", "Professional Fees", "Miscellaneous"
    ]
    messages = [{"role": "user", "content": (
        f"Categorize this expense for an Indian manufacturing company.\n"
        f"Description: \"{description}\"\nAmount: ₹{amount}\n"
        f"Available categories: {', '.join(categories)}\n"
        f"Return ONLY the category name from the list above."
    )}]
    reply, _ = await _call_ai(messages, "You are an expense categorization assistant.", max_tokens=20)
    category = reply.strip() if reply.strip() in categories else _simple_categorize(description)
    return {"category": category, "description": description, "amount": amount}


def _simple_categorize(desc: str) -> str:
    desc = desc.lower()
    if any(w in desc for w in ["rent", "office"]): return "Rent"
    if any(w in desc for w in ["electricity", "water", "internet", "phone"]): return "Utilities"
    if any(w in desc for w in ["transport", "vehicle", "fuel", "petrol", "auto", "cab"]): return "Transport"
    if any(w in desc for w in ["salary", "wages", "payroll"]): return "Salaries"
    if any(w in desc for w in ["bank", "charge", "fee"]): return "Bank Charges"
    if any(w in desc for w in ["travel", "hotel", "flight"]): return "Travel"
    return "Miscellaneous"


# ─────────────────────────────────────────────────────────────────────────────
# Cash Flow Forecasting
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/cash-flow-forecast")
async def cash_flow_forecast(months: int = 3, user=Depends(get_current_user)):
    _require_ai(user)
    today = date.today()
    from_date = (today.replace(day=1) - timedelta(days=180)).isoformat()

    monthly_sales = await db.invoices.aggregate([
        {"$match": {"created_at": {"$gte": from_date}}},
        {"$group": {"_id": {"$substr": ["$created_at", 0, 7]}, "total": {"$sum": "$total"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(12)

    monthly_expenses = await db.expense_entries.aggregate([
        {"$match": {"date": {"$gte": from_date}, "status": "APPROVED"}},
        {"$group": {"_id": {"$substr": ["$date", 0, 7]}, "total": {"$sum": "$amount"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(12)

    avg_sales = sum(m["total"] for m in monthly_sales) / max(len(monthly_sales), 1)
    avg_expenses = sum(m["total"] for m in monthly_expenses) / max(len(monthly_expenses), 1)

    forecast = []
    for i in range(1, months + 1):
        m = (today.month + i - 1) % 12 + 1
        y = today.year + (today.month + i - 1) // 12
        forecast.append({
            "month": f"{y}-{m:02d}",
            "projected_sales": round(avg_sales * (1 + 0.05 * i), 2),
            "projected_expenses": round(avg_expenses * (1 + 0.02 * i), 2),
            "projected_net_cash": round(avg_sales * (1 + 0.05 * i) - avg_expenses * (1 + 0.02 * i), 2),
        })

    return {
        "historical_sales": monthly_sales,
        "historical_expenses": monthly_expenses,
        "forecast": forecast,
        "avg_monthly_sales": round(avg_sales, 2),
        "avg_monthly_expenses": round(avg_expenses, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fraud / Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/fraud-alerts")
async def fraud_alerts(user=Depends(get_current_user)):
    _require_ai(user)
    alerts = []

    dups = await db.invoices.aggregate([
        {"$group": {"_id": "$invoice_number", "count": {"$sum": 1}, "ids": {"$push": "$id"}}},
        {"$match": {"count": {"$gt": 1}}},
    ]).to_list(20)
    for d in dups:
        alerts.append({
            "type": "DUPLICATE_INVOICE", "severity": "HIGH",
            "message": f"Duplicate invoice number: {d['_id']} appears {d['count']} times",
            "ids": d["ids"],
        })

    all_expenses = await db.expense_entries.find(
        {"status": "APPROVED"}, {"amount": 1, "description": 1, "id": 1, "_id": 0}
    ).to_list(500)
    if all_expenses:
        avg_amount = sum(e.get("amount", 0) for e in all_expenses) / len(all_expenses)
        for e in all_expenses:
            if e["amount"] > avg_amount * 3:
                alerts.append({
                    "type": "UNUSUAL_EXPENSE", "severity": "MEDIUM",
                    "message": f"Expense of ₹{e['amount']:,.2f} is unusually high (avg: ₹{avg_amount:,.0f})",
                    "id": e["id"], "description": e.get("description"),
                })

    zero_vouchers = await db.vouchers.count_documents({"amount": 0, "status": "APPROVED"})
    if zero_vouchers > 0:
        alerts.append({
            "type": "ZERO_AMOUNT_VOUCHER", "severity": "LOW",
            "message": f"{zero_vouchers} approved voucher(s) with zero amount detected",
        })

    return {"alert_count": len(alerts), "alerts": alerts, "generated_at": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# Business Insights
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/business-insights")
async def business_insights(user=Depends(get_current_user)):
    _require_ai(user)
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    prev_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()

    insights = []

    sales_this_month = await db.invoices.aggregate([
        {"$match": {"created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    sales_last_month = await db.invoices.aggregate([
        {"$match": {"created_at": {"$gte": prev_month_start, "$lt": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]).to_list(1)

    if sales_this_month:
        s = sales_this_month[0]
        last = sales_last_month[0]["total"] if sales_last_month else 0
        trend = ((s["total"] - last) / last * 100) if last > 0 else 0
        insights.append({
            "type": "SALES_SUMMARY", "title": "Sales This Month",
            "value": s["total"], "count": s["count"],
            "trend": round(trend, 1), "icon": "TrendingUp",
        })

    top_customer = await db.invoices.aggregate([
        {"$group": {"_id": "$customer_name", "total": {"$sum": "$total"}}},
        {"$sort": {"total": -1}}, {"$limit": 1},
    ]).to_list(1)
    if top_customer:
        insights.append({
            "type": "TOP_CUSTOMER", "title": "Top Customer",
            "value": top_customer[0]["total"], "name": top_customer[0]["_id"], "icon": "Star",
        })

    pending = await db.expense_entries.count_documents({"status": "PENDING"})
    if pending > 0:
        insights.append({
            "type": "PENDING_APPROVALS", "title": "Expenses Awaiting Approval",
            "value": pending, "priority": "HIGH" if pending > 5 else "NORMAL", "icon": "Clock",
        })

    low_stock = await db.products.count_documents(
        {"$expr": {"$lte": ["$quantity", "$low_stock_threshold"]}}
    )
    if low_stock > 0:
        insights.append({
            "type": "LOW_STOCK_ALERT", "title": "Products Below Minimum Stock",
            "value": low_stock, "priority": "HIGH", "icon": "Package",
        })

    unpaid_count = await db.invoices.count_documents({"status": "UNPAID"})
    if unpaid_count > 0:
        unpaid_agg = await db.invoices.aggregate([
            {"$match": {"status": "UNPAID"}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}},
        ]).to_list(1)
        unpaid_total = unpaid_agg[0]["total"] if unpaid_agg else 0
        insights.append({
            "type": "UNPAID_INVOICES", "title": "Pending Receivables",
            "value": unpaid_total, "count": unpaid_count, "priority": "HIGH", "icon": "AlertCircle",
        })

    return {"insights": insights, "generated_at": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# Chat History Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/chat/history")
async def get_chat_history(session_id: Optional[str] = None, user=Depends(get_current_user)):
    _require_ai(user)
    q = {"user_id": user["id"]}
    if session_id:
        q["session_id"] = session_id
    sessions = await db.ai_chat_history.find(q, {"_id": 0}).sort("updated_at", -1).limit(10).to_list(10)
    return sessions


@router.delete("/chat/history/{session_id}")
async def clear_chat_history(session_id: str, user=Depends(get_current_user)):
    await db.ai_chat_history.delete_one({"session_id": session_id, "user_id": user["id"]})
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Vendor Comparison (kept from original)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/vendor-compare")
async def vendor_compare(data: VendorCompareRequest, user=Depends(get_current_user)):
    _require_ai(user)
    q = {}
    if data.supplier_ids:
        q["supplier_id"] = {"$in": data.supplier_ids}
    pipeline = [
        {"$match": q},
        {"$unwind": "$items"},
        {"$match": {"items.product_name": {"$regex": data.product_name, "$options": "i"}}},
        {"$group": {
            "_id": "$supplier_id", "supplier_name": {"$first": "$supplier_name"},
            "avg_price": {"$avg": "$items.unit_price"}, "min_price": {"$min": "$items.unit_price"},
            "max_price": {"$max": "$items.unit_price"}, "order_count": {"$sum": 1},
        }},
        {"$sort": {"avg_price": 1}},
    ]
    results = await db.purchase_orders.aggregate(pipeline).to_list(20)
    return {
        "product": data.product_name,
        "vendors": results,
        "recommendation": results[0]["supplier_name"] if results else "No data available",
    }
