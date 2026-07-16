"""Public website lead capture — no auth.

The marketing site's "Book a Demo / Contact" form posts here. Submissions land
in the CRM `leads` collection (source = "Website") so sales sees them in the
Leads module. Unauthenticated by design, so it is rate-limited per IP and the
input is tightly bounded to avoid abuse / spam.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from core.rate_limit import rate_limit, client_ip
from core.utils import crud_create

router = APIRouter(prefix="/public", tags=["Public Website"])


class DemoRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company_name: str = Field(min_length=1, max_length=160)
    industry: Optional[str] = Field(default=None, max_length=80)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=30)
    num_users: Optional[int] = Field(default=None, ge=1, le=100000)
    requirements: Optional[str] = Field(default=None, max_length=2000)
    # Honeypot: real users never fill this hidden field; bots often do.
    website: Optional[str] = Field(default=None, max_length=200)


@router.post("/demo-request")
async def submit_demo_request(payload: DemoRequest, request: Request):
    """Create a CRM lead from a website demo/contact submission."""
    # Silently accept (and drop) honeypot hits so bots don't learn they failed.
    if payload.website:
        return {"ok": True}

    rate_limit(f"demo-request:{client_ip(request)}", limit=5, window_seconds=600, request=request)

    # Compose a notes block from the marketing-specific fields the Lead model
    # doesn't have first-class columns for.
    note_parts = []
    if payload.industry:
        note_parts.append(f"Industry: {payload.industry}")
    if payload.num_users:
        note_parts.append(f"Users: {payload.num_users}")
    if payload.requirements:
        note_parts.append(f"Requirements: {payload.requirements}")
    notes = " | ".join(note_parts) if note_parts else None

    lead = {
        "company_name": payload.company_name,
        "contact_person": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "source": "Website",
        "interested_in": payload.industry,
        "status": "NEW",
        "notes": notes,
        "estimated_value": 0,
    }
    try:
        created = await crud_create("leads", lead, user=None)
    except Exception:
        raise HTTPException(500, "Could not submit your request. Please try again.")

    return {"ok": True, "lead_id": created.get("id")}
