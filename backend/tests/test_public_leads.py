"""Public website lead-capture endpoint.

Pure unit tests — no live DB; crud_create is monkeypatched. Covers the
form→CRM-lead mapping, honeypot handling, and input validation.
"""
import os
import sys

os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from pydantic import ValidationError
from typing import cast
from fastapi import Request

import routers.public_leads as pl
from routers.public_leads import DemoRequest, submit_demo_request


class _Req:
    """Minimal stand-in for FastAPI Request (rate_limit reads headers/client)."""
    headers = {"x-test-bypass": "true"}
    client = None


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def captured(monkeypatch):
    """Capture the lead dict passed to crud_create instead of hitting the DB."""
    box = {}
    async def fake_create(collection, doc, user=None):
        box["collection"] = collection
        box["doc"] = doc
        box["user"] = user
        return {**doc, "id": "lead-123"}
    monkeypatch.setattr(pl, "crud_create", fake_create)
    return box


# ══════════════════════════════════════════════════════════════
# Model validation
# ══════════════════════════════════════════════════════════════

class TestModel:
    def test_minimal_valid(self):
        d = DemoRequest(name="Asha", company_name="Acme", email="a@acme.com")
        assert d.email == "a@acme.com"

    def test_bad_email_rejected(self):
        with pytest.raises(ValidationError):
            DemoRequest(name="x", company_name="y", email="nope")

    def test_num_users_bounds(self):
        with pytest.raises(ValidationError):
            DemoRequest(name="x", company_name="y", email="a@b.com", num_users=0)  # type: ignore


# ══════════════════════════════════════════════════════════════
# Endpoint behaviour
# ══════════════════════════════════════════════════════════════

class TestSubmit:
    def test_creates_website_lead(self, captured):
        payload = DemoRequest(
            name="Asha Rao", company_name="Acme Forge", industry="Forging & Casting",
            email="asha@acme.com", phone="+91 99", num_users=25, requirements="Need GST",
        )
        out = _run(submit_demo_request(payload, cast(Request, _Req())))
        assert out["ok"] is True
        assert out["lead_id"] == "lead-123"
        doc = captured["doc"]
        assert captured["collection"] == "leads"
        assert doc["company_name"] == "Acme Forge"
        assert doc["contact_person"] == "Asha Rao"
        assert doc["source"] == "Website"
        assert doc["status"] == "NEW"
        # marketing-only fields are folded into notes
        assert "Industry: Forging & Casting" in doc["notes"]
        assert "Users: 25" in doc["notes"]
        assert "Requirements: Need GST" in doc["notes"]

    def test_no_extra_fields_means_no_notes(self, captured):
        payload = DemoRequest(name="A", company_name="B", email="a@b.com")
        _run(submit_demo_request(payload, cast(Request, _Req())))
        assert captured["doc"]["notes"] is None

    def test_honeypot_drops_silently(self, captured):
        # A filled honeypot returns ok but must NOT create a lead.
        payload = DemoRequest(name="bot", company_name="bot", email="b@b.com", website="spam")
        out = _run(submit_demo_request(payload, cast(Request, _Req())))
        assert out == {"ok": True}
        assert "doc" not in captured  # crud_create never called
